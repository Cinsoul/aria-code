package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"os"

	"github.com/artheras/aria-code/go/runtime/quant"
)

type backtestInput struct {
	Data         json.RawMessage `json:"data"`
	Strategy     string          `json:"strategy"`
	StartingCash *float64        `json:"starting_cash"`
	Commission   *float64        `json:"commission"`
	Slippage     *float64        `json:"slippage"`
	Periods      int             `json:"periods_per_year"`
	Fast         int             `json:"fast"`
	Slow         int             `json:"slow"`
	Weight       *float64        `json:"weight"`
}

func orderedSeries(raw json.RawMessage) ([]quant.Series, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	token, err := decoder.Token()
	if err != nil || token != json.Delim('{') {
		return nil, errors.New("data must be an object of symbol/bar arrays")
	}
	series := []quant.Series{}
	seen := map[string]bool{}
	for decoder.More() {
		key, err := decoder.Token()
		if err != nil {
			return nil, err
		}
		symbol, ok := key.(string)
		if !ok || seen[symbol] {
			return nil, errors.New("invalid or duplicate symbol")
		}
		seen[symbol] = true
		var bars []quant.Bar
		if err := decoder.Decode(&bars); err != nil {
			return nil, err
		}
		series = append(series, quant.Series{Symbol: symbol, Bars: bars})
	}
	if _, err := decoder.Token(); err != nil {
		return nil, err
	}
	return series, nil
}
func runBacktest(input backtestInput) (quant.Result, error) {
	data, err := orderedSeries(input.Data)
	if err != nil {
		return quant.Result{}, err
	}
	engine := quant.DefaultEngine()
	if input.StartingCash != nil {
		engine.StartingCash = *input.StartingCash
	}
	if input.Commission != nil {
		engine.Commission = *input.Commission
	}
	if input.Slippage != nil {
		engine.Slippage = *input.Slippage
	}
	if input.Periods != 0 {
		engine.PeriodsPerYear = input.Periods
	}
	name := input.Strategy
	if name == "" {
		name = "buy_hold"
	}
	strategy, err := quant.NewStrategy(name, input.Fast, input.Slow, input.Weight)
	if err != nil {
		return quant.Result{}, err
	}
	return engine.Run(data, strategy)
}
func backtestCommand(args []string) int {
	if len(args) != 2 || args[0] != "--input" {
		json.NewEncoder(os.Stderr).Encode(map[string]any{"error": "usage: aria-runtime backtest --input data.json"})
		return 2
	}
	var input backtestInput
	if err := readJSON(args[1], &input); err != nil {
		json.NewEncoder(os.Stderr).Encode(map[string]any{"error": err.Error()})
		return 2
	}
	result, err := runBacktest(input)
	if err != nil {
		json.NewEncoder(os.Stderr).Encode(map[string]any{"error": err.Error()})
		return 2
	}
	if err := json.NewEncoder(os.Stdout).Encode(result); err != nil {
		return 1
	}
	return 0
}
