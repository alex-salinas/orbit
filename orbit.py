#!/usr/bin/env python3
"""Orbit — a small, dependency-free terminal IDE.

Run with: python3 orbit.py [directory]
"""
import curses
import os
import re
import shlex
import queue
import signal
import subprocess
import sys
import termios
import threading
from pathlib import Path

KEYWORDS = re.compile(r"\b(and|as|assert|async|await|break|class|const|def|elif|else|except|export|finally|for|from|function|if|import|in|let|lambda|new|not|or|pass|return|switch|try|var|while|with|yield)\b")
STRINGS = re.compile(r"(['\"])(?:\\.|(?!\1).)*\1")
COMMENTS = re.compile(r"(#.*$|//.*$)")


class Buffer:
    def __init__(self, path: Path):
        self.path = path
        try:
            self.lines = path.read_text(errors="replace").splitlines() or [""]
        except (OSError, UnicodeError):
            self.lines = [""]
        self.row = self.col = self.top = self.left = 0
        self.dirty = False

    @property
    def title(self):
        return self.path.name + (" ●" if self.dirty else "")

    def save(self):
        self.path.write_text("\n".join(self.lines) + "\n")
        self.dirty = False


class Orbit:
    def __init__(self, stdscr, root: Path):
        self.s = stdscr
        self.root = root.resolve()
        self.tree = []
        self.buffers = []
        self.active = 0
        self.focus = "tree"
        self.message = "F1 help  •  F2 files  •  F3 shell  •  F5 ssh  •  Ctrl-S save"
        self.term_lines = ["Orbit shell ready. Type a command and press Enter."]
        self.command = ""
        self.term_scroll = 0
        self.process = None
        self.process_output = queue.Queue()
        self.tree_index = 0
        self.show_hidden = False
        self.running = True
        self.setup_colors()
        self.refresh_tree()

    def setup_colors(self):
        curses.start_color(); curses.use_default_colors()
        pairs = [(1, curses.COLOR_BLACK, curses.COLOR_CYAN), (2, curses.COLOR_CYAN, -1),
                 (3, curses.COLOR_YELLOW, -1), (4, curses.COLOR_MAGENTA, -1),
                 (5, curses.COLOR_GREEN, -1), (6, curses.COLOR_BLUE, -1), (7, curses.COLOR_WHITE, curses.COLOR_BLUE)]
        for i, fg, bg in pairs: curses.init_pair(i, fg, bg)

    def refresh_tree(self):
        self.tree = []
        def visit(directory, depth):
            try: entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except OSError: return
            for p in entries:
                if not self.show_hidden and p.name.startswith("."): continue
                self.tree.append((p, depth, p.is_dir()))
                if p.is_dir() and depth < 4: visit(p, depth + 1)
        visit(self.root, 0)
        self.tree_index = min(self.tree_index, max(0, len(self.tree)-1))

    def open_file(self, path):
        if path.is_dir(): return
        for i, buf in enumerate(self.buffers):
            if buf.path == path: self.active = i; self.focus = "editor"; return
        self.buffers.append(Buffer(path)); self.active = len(self.buffers)-1; self.focus = "editor"

    def new_file(self):
        """Create a project-local file and immediately open it in a tab."""
        name = self.ask("New file (relative to project): ")
        if not name:
            return
        target = (self.root / name).resolve()
        try:
            target.relative_to(self.root)
        except ValueError:
            self.message = "New files must be inside the project folder"
            return
        if target.exists():
            self.message = f"Already exists: {target.name}"
            self.open_file(target)
            return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
            self.refresh_tree()
            self.open_file(target)
            self.message = f"Created {target.relative_to(self.root)}"
        except OSError as error:
            self.message = f"Could not create file: {error}"

    def active_buffer(self): return self.buffers[self.active] if self.buffers else None

    def draw(self):
        self.s.erase(); h, w = self.s.getmaxyx()
        if h < 12 or w < 55:
            self.s.addstr(0, 0, "Orbit needs a terminal of at least 55×12.")
            self.s.refresh(); return
        side = max(22, min(34, w // 4)); term_h = max(7, h // 4); edit_bottom = h - term_h - 2
        self.s.attron(curses.color_pair(1) | curses.A_BOLD)
        self.s.addnstr(0, 0, " ◈ ORBIT  ", w); self.s.addnstr(0, 12, str(self.root), w-12); self.s.attroff(curses.color_pair(1) | curses.A_BOLD)
        self.draw_tree(1, side, edit_bottom)
        self.draw_editor(side + 1, 1, w - side - 1, edit_bottom - 1)
        self.draw_terminal(1, edit_bottom + 1, w - 2, term_h)
        status = f" {self.focus.upper()}  {self.message}"
        # ncurses returns ERR when a write fills the lower-right screen cell.
        # Keep one column free so the status bar works in every terminal emulator.
        self.s.attron(curses.color_pair(7))
        try:
            self.s.addnstr(h-1, 0, status.ljust(max(0, w-1)), max(0, w-1))
        except curses.error:
            pass
        self.s.attroff(curses.color_pair(7))
        self.s.refresh()

    def draw_tree(self, x, width, bottom):
        title = " FILES " + ("[focus]" if self.focus == "tree" else "")
        self.s.attron(curses.A_BOLD); self.s.addnstr(1, x, title, width-1); self.s.attroff(curses.A_BOLD)
        for screen_y, (path, depth, is_dir) in enumerate(self.tree[:bottom-2], 2):
            idx = screen_y - 2; marker = "▾ " if is_dir else "  "; name = ("▣ " if is_dir else "· ") + path.name
            text = " " * (depth * 2) + marker + name
            style = curses.A_REVERSE if idx == self.tree_index and self.focus == "tree" else 0
            if is_dir: style |= curses.color_pair(3)
            try: self.s.addnstr(screen_y, x, text.ljust(width-1), width-1, style)
            except curses.error: pass
        for y in range(1, bottom):
            try: self.s.addch(y, width, curses.ACS_VLINE)
            except curses.error: pass

    def highlight_line(self, line, x, y, width):
        # Curses rendering with token colors; compact and intentionally language-agnostic.
        # Match offsets are relative to the whole source line, so clip them before
        # using them as screen coordinates (long lines otherwise exceed the pane).
        visible = max(0, width - 1)
        matches = []
        for rx, color in ((COMMENTS, 5), (STRINGS, 3), (KEYWORDS, 4)):
            matches += [(m.start(), m.end(), color) for m in rx.finditer(line)]
        matches.sort()
        pos = 0
        for a, b, color in matches:
            if a < pos or a >= visible: continue
            b = min(b, visible)
            try:
                self.s.addnstr(y, x + pos, line[pos:a], a - pos)
                self.s.addnstr(y, x + a, line[a:b], b - a, curses.color_pair(color))
            except curses.error:
                pass
            pos = b
        if pos < visible:
            try: self.s.addnstr(y, x + pos, line[pos:visible], visible - pos)
            except curses.error: pass

    def draw_editor(self, x, y, width, height):
        buf = self.active_buffer()
        tabs = " ".join((f"[{b.title}]" if i == self.active else b.title) for i, b in enumerate(self.buffers)) or "  No file open — choose one in FILES"
        self.s.attron(curses.A_BOLD); self.s.addnstr(y, x, tabs, width); self.s.attroff(curses.A_BOLD)
        if not buf: return
        view_h = height - 1; buf.top = max(0, min(buf.top, max(0, len(buf.lines)-view_h)))
        for i in range(view_h):
            r = buf.top + i
            if r >= len(buf.lines): break
            num = f"{r+1:>4} "
            self.s.addnstr(y+1+i, x, num, 5, curses.color_pair(2))
            self.highlight_line(buf.lines[r][buf.left:], x+5, y+1+i, width-5)
        if self.focus == "editor":
            cy = y + 1 + buf.row - buf.top; cx = x + 5 + buf.col - buf.left
            if y+1 <= cy < y+height and x+5 <= cx < x+width:
                # Render a software caret too: some terminal themes hide the
                # hardware cursor against a syntax-highlighted background.
                try:
                    caret = buf.lines[buf.row][buf.col:buf.col+1] or " "
                    self.s.addnstr(cy, cx, caret, 1, curses.A_REVERSE)
                    self.s.move(cy, cx)
                except curses.error: pass

    def draw_terminal(self, x, y, width, height):
        self.s.hline(y-1, x, curses.ACS_HLINE, width)
        running = f" ● pid {self.process.pid} — Ctrl-C stop" if self.process else ""
        title = " SHELL " + ("[focus]" if self.focus == "terminal" else "") + running
        self.s.addnstr(y, x, title, width, curses.A_BOLD)
        visible = self.term_lines[-(height-3):]
        for i, line in enumerate(visible, 1):
            self.s.addnstr(y+i, x, line, width)
        prompt = f"$ {self.command}" if self.focus == "terminal" else "$"
        self.s.addnstr(y+height-1, x, prompt, width, curses.color_pair(5))
        if self.focus == "terminal":
            try: self.s.move(y+height-1, min(x+2+len(self.command), x+width-1))
            except curses.error: pass

    def run_command(self):
        cmd = self.command.strip(); self.command = ""
        if not cmd: return
        self.term_lines.append(f"$ {cmd}")
        if cmd in ("clear", "cls"): self.term_lines = []; return
        if cmd.startswith(":ssh "):
            self.open_ssh(cmd[5:].strip()); return
        if self.process:
            self.term_lines.append("A command is already running. Press Ctrl-C to stop it.")
            return
        try:
            process = subprocess.Popen(cmd, shell=True, cwd=self.root, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            self.process = process
            threading.Thread(target=self.collect_process_output, args=(process,), daemon=True).start()
        except OSError as err: self.term_lines.append(f"Error: {err}")

    def collect_process_output(self, process):
        if process.stdout:
            for line in process.stdout:
                self.process_output.put((process, line.rstrip()))
        self.process_output.put((process, f"[process exited: {process.wait()}]"))

    def drain_process_output(self):
        while True:
            try: process, line = self.process_output.get_nowait()
            except queue.Empty: break
            self.term_lines.append(line)
            if line.startswith("[process exited:") and self.process is process:
                self.process = None

    def stop_process(self):
        if not self.process:
            self.command = ""
            return
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
            self.term_lines.append("[stopping process]")
        except ProcessLookupError:
            pass

    def open_ssh(self, host=None):
        if not host: host = self.ask("SSH host (uses ~/.ssh/config): ")
        if not host: return
        self.s.def_prog_mode(); curses.endwin()
        try:
            subprocess.run(["ssh", "-tt", host])
        finally:
            self.s.reset_prog_mode(); curses.curs_set(1); self.message = f"Returned from SSH session: {host}"

    def ask(self, prompt):
        h, w = self.s.getmaxyx(); self.s.addnstr(h-2, 0, prompt.ljust(w), w, curses.color_pair(7)); self.s.refresh()
        curses.echo(); curses.curs_set(1)
        try: result = self.s.getstr(h-2, min(len(prompt), w-1), w-len(prompt)-1).decode()
        except curses.error: result = ""
        curses.noecho(); return result.strip()

    def edit_key(self, key):
        b = self.active_buffer()
        if not b: return
        if key == 19: # Ctrl-S
            try: b.save(); self.message = f"Saved {b.path.name}"
            except OSError as e: self.message = f"Save failed: {e}"
        elif key in (curses.KEY_HOME, 1): b.col = 0 # Home / Ctrl-A
        elif key in (curses.KEY_END, 5): b.col = len(b.lines[b.row]) # End / Ctrl-E
        elif key in (curses.KEY_LEFT,): b.col = max(0, b.col-1)
        elif key in (curses.KEY_RIGHT,): b.col = min(len(b.lines[b.row]), b.col+1)
        elif key == curses.KEY_UP: b.row = max(0, b.row-1); b.col = min(b.col, len(b.lines[b.row]))
        elif key == curses.KEY_DOWN: b.row = min(len(b.lines)-1, b.row+1); b.col = min(b.col, len(b.lines[b.row]))
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if b.col: b.lines[b.row] = b.lines[b.row][:b.col-1]+b.lines[b.row][b.col:]; b.col -= 1; b.dirty = True
            elif b.row: b.col=len(b.lines[b.row-1]); b.lines[b.row-1]+=b.lines.pop(b.row); b.row-=1; b.dirty=True
        elif key in (10, 13, curses.KEY_ENTER):
            b.lines.insert(b.row+1, b.lines[b.row][b.col:]); b.lines[b.row]=b.lines[b.row][:b.col]; b.row+=1; b.col=0; b.dirty=True
        elif 32 <= key <= 126: b.lines[b.row] = b.lines[b.row][:b.col]+chr(key)+b.lines[b.row][b.col:]; b.col+=1; b.dirty=True
        b.top = min(b.top, b.row); b.top = b.row if b.row > b.top + 20 else b.top

    def handle(self, key):
        if key == 17: self.running = False # Ctrl-Q
        elif key == 14: self.new_file() # Ctrl-N
        elif key == curses.KEY_F1: self.message = "Ctrl-N new file • Ctrl-Q quit • Ctrl-S save • Home/End (or Ctrl-A/E) line start/end • Ctrl-C stops shell"
        elif key == curses.KEY_F2: self.focus = "tree"
        elif key == curses.KEY_F3: self.focus = "terminal"
        elif key == curses.KEY_F5: self.open_ssh()
        elif key == 9: self.focus = {"tree":"editor", "editor":"terminal", "terminal":"tree"}[self.focus]
        elif key in (ord('q'),) and self.focus == "tree": self.running = False
        elif self.focus == "tree":
            if key == curses.KEY_UP: self.tree_index=max(0,self.tree_index-1)
            elif key == curses.KEY_DOWN: self.tree_index=min(len(self.tree)-1,self.tree_index+1)
            elif key in (10,13,curses.KEY_ENTER) and self.tree: self.open_file(self.tree[self.tree_index][0])
            elif key == ord('r'): self.refresh_tree(); self.message="File tree refreshed"
        elif self.focus == "editor": self.edit_key(key)
        else:
            if key == 3: self.stop_process() # Ctrl-C
            elif key in (curses.KEY_HOME, 1): self.command = ""
            elif key in (curses.KEY_END, 5): pass
            elif key in (10,13,curses.KEY_ENTER): self.run_command()
            elif key in (curses.KEY_BACKSPACE,127,8): self.command=self.command[:-1]
            elif 32 <= key <= 126: self.command += chr(key)

    def loop(self):
        try: curses.curs_set(2)
        except curses.error: pass
        self.s.keypad(True); self.s.timeout(100); curses.mousemask(curses.ALL_MOUSE_EVENTS)
        while self.running:
            self.drain_process_output(); self.draw(); key = self.s.getch()
            if key == -1: continue
            if key == curses.KEY_MOUSE:
                try:
                    _, mx, my, _, state = curses.getmouse(); h,w=self.s.getmaxyx(); side=max(22,min(34,w//4)); term_y=h-max(7,h//4)-1
                    if state & curses.BUTTON1_CLICKED:
                        if my >= term_y: self.focus="terminal"
                        elif mx <= side and my >= 2: self.focus="tree"; self.tree_index=min(max(0,my-2),len(self.tree)-1)
                        else: self.focus="editor"
                except curses.error: pass
            else: self.handle(key)
        self.stop_process()


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    if not root.is_dir(): print(f"Not a directory: {root}", file=sys.stderr); return 2
    # Ctrl-S is XOFF by default in many macOS terminals. Disable it while
    # Orbit runs so the editor receives the save shortcut, then restore it.
    stdin = sys.stdin.fileno()
    original_termios = termios.tcgetattr(stdin)
    active_termios = termios.tcgetattr(stdin)
    active_termios[0] &= ~termios.IXON
    termios.tcsetattr(stdin, termios.TCSADRAIN, active_termios)
    try:
        curses.wrapper(lambda screen: Orbit(screen, root).loop())
    finally:
        termios.tcsetattr(stdin, termios.TCSADRAIN, original_termios)
    return 0

if __name__ == "__main__": raise SystemExit(main())
