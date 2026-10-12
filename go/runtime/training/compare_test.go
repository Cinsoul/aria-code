package training

import "testing"

func TestStatisticsKeepErrorsOutOfScoresAndCosts(t *testing.T) {
	r := Compare([]Report{{Results: []Attempt{{"one", "pass", 10}, {"one", "error", 999}, {"two", "fail", 20}}}}, []Report{{Results: []Attempt{{"one", "pass", 10}, {"one", "invalid", 999}, {"two", "pass", 20}}}})
	if r.Tasks != 2 || r.Better != 1 || r.Same != 1 || *r.BaselineRate != 0.5 || *r.CandidateRate != 1 || r.MeanSeconds["baseline"] != 15 || r.Unscored["baseline"]["error"] != 1 {
		t.Fatal(r)
	}
	if r.Improved {
		t.Fatal("an interval containing zero was claimed to be an improvement")
	}
}
func TestExactSignTestAndAllTies(t *testing.T) {
	if SignTest(0, 0) != 1 || SignTest(10, 0) != 2.0/1024 {
		t.Fatal("sign-test contract changed")
	}
	if got := BootstrapCI([]float64{0, 0, 0}); got != [2]float64{} {
		t.Fatal(got)
	}
}
func TestBootstrapRandomStreamMatchesTheExistingFixedSeed(t *testing.T) {
	r := newRandom(7)
	for _, expected := range []uint32{1390851128, 4071050724, 647892279, 1695753998, 2795742288} {
		if got := r.word(); got != expected {
			t.Fatal("bootstrap generator differs from CPython", got, expected)
		}
	}
}
