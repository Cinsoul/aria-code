package quant

import (
	"errors"
	"math"
	"testing"
)

type strategyFunc struct {
	callback func(Context) ([]Order, error)
}

func (s strategyFunc) Name() string                     { return "custom" }
func (s strategyFunc) OnBar(c Context) ([]Order, error) { return s.callback(c) }
func TestCustomStrategyUsesNextOpenAndCannotChangeEnginePositions(t *testing.T) {
	engine := Engine{1000, 0, 0, 252}
	calls := 0
	strategy := strategyFunc{func(c Context) ([]Order, error) {
		calls++
		c.Portfolio.Positions["AAA"] = 999999
		if calls == 1 {
			return []Order{{Symbol: "AAA", Action: "buy", Quantity: 20}}, nil
		}
		if calls == 2 {
			return []Order{{Symbol: "AAA", Action: "sell", Quantity: 10}}, nil
		}
		return nil, nil
	}}
	result, err := engine.Run([]Series{{"AAA", []Bar{{Date: "1", Open: 10, Close: 10}, {Date: "2", Open: 20, Close: 20}, {Date: "3", Open: 30, Close: 30}}}}, strategy)
	if err != nil || len(result.Trades) != 2 || result.Trades[0].Price != 20 || result.Trades[1].Price != 30 || result.Equity[2].Equity != 1200 {
		t.Fatal(result, err)
	}
	if result.Trades[1].RealizedPnL == nil || *result.Trades[1].RealizedPnL != 100 {
		t.Fatal("realized PnL incorrect")
	}
}
func TestStrategyErrorsDoNotFabricateOrdersAndInvalidDataFails(t *testing.T) {
	e := DefaultEngine()
	data := []Series{{"AAA", []Bar{{Date: "1", Open: 10, Close: 10}, {Date: "2", Open: 20, Close: 20}}}}
	r, err := e.Run(data, strategyFunc{func(Context) ([]Order, error) { return nil, errors.New("no signal") }})
	if err != nil || len(r.Trades) != 0 || r.Equity[1].Equity != e.StartingCash {
		t.Fatal(r, err)
	}
	data[0].Bars[0].Open = math.NaN()
	if _, err := e.Run(data, &BuyHold{Weight: 1}); err == nil {
		t.Fatal("non-finite price accepted")
	}
}
func TestRoundingAndBrokerIntentParity(t *testing.T) {
	if round(2.675, 2) != 2.67 {
		t.Fatal("rounding differs from the existing engine")
	}
	weight, price := 0.5, 100.0
	buy := ToIntent(Order{Symbol: "AAPL", Action: "buy", Quantity: 10}, &price, "strategy")
	if buy.Side != "buy" || *buy.Quantity != 10 || *buy.Price != 100 {
		t.Fatal(buy)
	}
	target := ToIntent(Order{Symbol: "AAPL", Action: "target", TargetWeight: &weight}, nil, "strategy")
	if target.Quantity != nil || *target.TargetWeight != 0.5 {
		t.Fatal(target)
	}
}
