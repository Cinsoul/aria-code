package main

import (
	"context"
	"os"
	"os/exec"
	"strconv"
	"time"
)

func configureCommandTree(cmd *exec.Cmd) {
	cmd.Cancel = func() error {
		stopCommandTree(cmd)
		if cmd.Process == nil {
			return os.ErrProcessDone
		}
		return cmd.Process.Kill()
	}
}
func stopCommandTree(cmd *exec.Cmd) {
	if cmd.Process == nil {
		return
	}
	if cmd.ProcessState != nil && cmd.ProcessState.Exited() {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	_ = exec.CommandContext(ctx, "taskkill.exe", "/PID", strconv.Itoa(cmd.Process.Pid), "/T", "/F").Run()
}
