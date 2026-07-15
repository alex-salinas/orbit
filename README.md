# Orbit

A dependency-free terminal IDE for local folders and SSH sessions.

```sh
python3 orbit.py ~/code/project
```

## Controls

- `F1` help, `F2` files, `F3` shell, `F5` open an interactive SSH session
- `Tab` moves between file tree, editor, and command shell
- `Ctrl-N` creates a file relative to the project root; `Ctrl-Q` exits Orbit
- Arrow keys and Enter select a file; `r` refreshes the tree
- `Ctrl-S` saves the open file
- In the shell, execute any local command in the project directory
- Use `:ssh host-alias` in the shell (or `F5`) to enter an interactive SSH session; the system `ssh` client uses your `~/.ssh/config`, agent, keys, proxy jumps, and MFA setup.

When the SSH session ends, Orbit resumes. For full-screen remote editors, run `micro`, `vim`, or another editor after connecting.
