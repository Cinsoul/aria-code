package training

import "math"

// Neumaier summation matches the current Python 3.13 oracle, including values
// near a decimal-rounding boundary. Keep the compensation separate until end.
type accurateSum struct{ high, low float64 }

func (s *accurateSum) add(value float64) {
	next := s.high + value
	if math.Abs(s.high) >= math.Abs(value) {
		s.low += (s.high - next) + value
	} else {
		s.low += (value - next) + s.high
	}
	s.high = next
}
func (s accurateSum) value() float64 {
	if s.low != 0 && !math.IsInf(s.low, 0) && !math.IsNaN(s.low) {
		return s.high + s.low
	}
	return s.high
}
