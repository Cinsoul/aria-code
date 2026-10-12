// Package training preserves offline dataset and evaluation business rules.
package training

import (
	"math"
	"math/big"
	"math/bits"
	"sort"
	"strconv"
)

type Attempt struct {
	TaskID  string  `json:"task_id"`
	Outcome string  `json:"outcome"`
	Seconds float64 `json:"seconds"`
}
type Report struct {
	Results []Attempt `json:"results"`
}
type TaskRates struct {
	Baseline  float64 `json:"baseline"`
	Candidate float64 `json:"candidate"`
}
type Comparison struct {
	Tasks          int                       `json:"tasks_compared"`
	BaselineRate   *float64                  `json:"baseline_pass_rate"`
	CandidateRate  *float64                  `json:"candidate_pass_rate"`
	MeanDifference float64                   `json:"mean_difference"`
	CI             [2]float64                `json:"ci95"`
	Better         int                       `json:"tasks_better"`
	Worse          int                       `json:"tasks_worse"`
	Same           int                       `json:"tasks_same"`
	SignP          float64                   `json:"sign_test_p"`
	Improved       bool                      `json:"improved"`
	OnlyBaseline   []string                  `json:"only_in_baseline"`
	OnlyCandidate  []string                  `json:"only_in_candidate"`
	Unscored       map[string]map[string]int `json:"unscored"`
	MeanSeconds    map[string]float64        `json:"mean_seconds"`
	PerTask        map[string]TaskRates      `json:"per_task"`
}

func rounded(n float64, places int) float64 {
	v, _ := strconv.ParseFloat(strconv.FormatFloat(n, 'f', places, 64), 64)
	return v
}
func Rates(reports []Report) (map[string]float64, map[string]int, float64) {
	passed, scored, unscored := map[string]int{}, map[string]int{}, map[string]int{}
	seconds := accurateSum{}
	attempts := 0
	for _, report := range reports {
		for _, r := range report.Results {
			if r.Outcome == "pass" || r.Outcome == "fail" {
				scored[r.TaskID]++
				if r.Outcome == "pass" {
					passed[r.TaskID]++
				}
				seconds.add(r.Seconds)
				attempts++
			} else {
				unscored[r.Outcome]++
			}
		}
	}
	rates := map[string]float64{}
	for id, count := range scored {
		rates[id] = float64(passed[id]) / float64(count)
	}
	mean := 0.0
	if attempts > 0 {
		mean = seconds.value() / float64(attempts)
	}
	return rates, unscored, mean
}

// CPython Random's MT19937 integer seeding and randbelow/getrandbits contract
// preserve the existing deterministic bootstrap draws, not only its mean.
type pythonRandom struct {
	state [624]uint32
	index int
}

func newRandom(seed uint32) *pythonRandom {
	r := &pythonRandom{index: 624}
	r.state[0] = 19650218
	for i := 1; i < 624; i++ {
		previous := r.state[i-1]
		r.state[i] = 1812433253*(previous^(previous>>30)) + uint32(i)
	}
	i := 1
	for k := 624; k > 0; k-- {
		previous := r.state[i-1]
		r.state[i] = (r.state[i] ^ ((previous ^ (previous >> 30)) * 1664525)) + seed
		i++
		if i >= 624 {
			r.state[0] = r.state[623]
			i = 1
		}
	}
	for k := 623; k > 0; k-- {
		previous := r.state[i-1]
		r.state[i] = (r.state[i] ^ ((previous ^ (previous >> 30)) * 1566083941)) - uint32(i)
		i++
		if i >= 624 {
			r.state[0] = r.state[623]
			i = 1
		}
	}
	r.state[0] = 0x80000000
	return r
}
func (r *pythonRandom) word() uint32 {
	if r.index >= 624 {
		for i := 0; i < 624; i++ {
			y := (r.state[i] & 0x80000000) | (r.state[(i+1)%624] & 0x7fffffff)
			r.state[i] = r.state[(i+397)%624] ^ (y >> 1)
			if y&1 != 0 {
				r.state[i] ^= 0x9908b0df
			}
		}
		r.index = 0
	}
	y := r.state[r.index]
	r.index++
	y ^= y >> 11
	y ^= (y << 7) & 0x9d2c5680
	y ^= (y << 15) & 0xefc60000
	y ^= y >> 18
	return y
}
func (r *pythonRandom) below(n int) int {
	k := bits.Len(uint(n))
	for {
		value := int(r.word() >> uint(32-k))
		if value < n {
			return value
		}
	}
}
func BootstrapCI(diffs []float64) [2]float64 {
	if len(diffs) == 0 {
		return [2]float64{}
	}
	rng := newRandom(7)
	means := make([]float64, 10000)
	for i := range means {
		sum := accurateSum{}
		for range diffs {
			sum.add(diffs[rng.below(len(diffs))])
		}
		means[i] = sum.value() / float64(len(diffs))
	}
	sort.Float64s(means)
	return [2]float64{means[250], means[9750]}
}
func SignTest(better, worse int) float64 {
	n := better + worse
	if n == 0 {
		return 1
	}
	k := min(better, worse)
	sum := new(big.Int)
	for i := 0; i <= k; i++ {
		sum.Add(sum, new(big.Int).Binomial(int64(n), int64(i)))
	}
	sum.Lsh(sum, 1)
	denominator := new(big.Int).Lsh(big.NewInt(1), uint(n))
	ratio := new(big.Rat).SetFrac(sum, denominator)
	value, _ := ratio.Float64()
	return math.Min(1, value)
}
func Compare(baseline, candidate []Report) Comparison {
	base, baseUnscored, baseSeconds := Rates(baseline)
	cand, candUnscored, candSeconds := Rates(candidate)
	common := []string{}
	onlyBase := []string{}
	onlyCand := []string{}
	for task := range base {
		if _, ok := cand[task]; ok {
			common = append(common, task)
		} else {
			onlyBase = append(onlyBase, task)
		}
	}
	for task := range cand {
		if _, ok := base[task]; !ok {
			onlyCand = append(onlyCand, task)
		}
	}
	sort.Strings(common)
	sort.Strings(onlyBase)
	sort.Strings(onlyCand)
	result := Comparison{Tasks: len(common), OnlyBaseline: onlyBase, OnlyCandidate: onlyCand, Unscored: map[string]map[string]int{"baseline": baseUnscored, "candidate": candUnscored}, MeanSeconds: map[string]float64{"baseline": rounded(baseSeconds, 1), "candidate": rounded(candSeconds, 1)}, PerTask: map[string]TaskRates{}}
	diffs := make([]float64, 0, len(common))
	baseSum, candSum, meanSum := accurateSum{}, accurateSum{}, accurateSum{}
	for _, task := range common {
		difference := cand[task] - base[task]
		diffs = append(diffs, difference)
		meanSum.add(difference)
		baseSum.add(base[task])
		candSum.add(cand[task])
		if difference > 0 {
			result.Better++
		} else if difference < 0 {
			result.Worse++
		}
		result.PerTask[task] = TaskRates{rounded(base[task], 3), rounded(cand[task], 3)}
	}
	if len(common) > 0 {
		n := float64(len(common))
		baseMean := rounded(baseSum.value()/n, 4)
		candMean := rounded(candSum.value()/n, 4)
		result.BaselineRate = &baseMean
		result.CandidateRate = &candMean
		result.MeanDifference = rounded(meanSum.value()/n, 4)
	}
	interval := BootstrapCI(diffs)
	result.Improved = interval[0] > 0
	result.CI = [2]float64{rounded(interval[0], 4), rounded(interval[1], 4)}
	result.Same = len(common) - result.Better - result.Worse
	result.SignP = rounded(SignTest(result.Better, result.Worse), 4)
	return result
}
