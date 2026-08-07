# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Iterable

from src.jb_quickpanel.features.global_hotkeys import HotkeyAction, hotkey_from_tk_event


MODE_LABELS = {
    "hwp": "일반 한글",
    "kedufine": "기안창",
}


class HotkeySettingsDialog:
    def __init__(
        self,
        parent,
        actions: Iterable[HotkeyAction],
        bindings: dict[str, str],
        on_save: Callable[[dict[str, str]], None],
        on_close: Callable[[bool], None],
    ):
        self.parent = parent
        self.actions = tuple(actions)
        self.action_by_id = {action.id: action for action in self.actions}
        self.bindings = dict(bindings)
        self.on_save = on_save
        self.on_close = on_close
        self.saved = False
        self._closed = False

        self.window = tk.Toplevel(parent)
        self.window.title("전역 단축키 설정")
        self.window.configure(bg="#f3f5f7")
        self.window.minsize(620, 500)
        self.window.resizable(True, True)
        try:
            self.window.transient(parent)
        except Exception:
            pass

        self.search_var = tk.StringVar()
        self.count_var = tk.StringVar()
        self._build_ui()
        self._refresh_tree()
        self._position_window()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.bind("<Destroy>", self._on_destroy, add="+")
        self.window.after(60, self.search_entry.focus_set)

    def _build_ui(self):
        body = ttk.Frame(self.window, padding=14)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="전역 단축키", font=("맑은 고딕", 12, "bold")).pack(anchor="w")
        ttk.Label(
            body,
            text="기능을 선택한 뒤 더블클릭하거나 '단축키 지정'을 누르세요. 프로그램이 트레이에 있어도 작동합니다.",
            foreground="#667085",
            wraplength=650,
            justify="left",
        ).pack(anchor="w", pady=(3, 12))

        search_row = ttk.Frame(body)
        search_row.pack(fill="x", pady=(0, 8))
        ttk.Label(search_row, text="기능 검색").pack(side="left", padx=(0, 8))
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_var.trace_add("write", lambda *_args: self._refresh_tree())

        tree_wrap = ttk.Frame(body)
        tree_wrap.pack(fill="both", expand=True)
        tree_wrap.rowconfigure(0, weight=1)
        tree_wrap.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            tree_wrap,
            columns=("category", "label", "target", "hotkey"),
            show="headings",
            selectmode="browse",
            height=18,
        )
        self.tree.heading("category", text="구분")
        self.tree.heading("label", text="기능")
        self.tree.heading("target", text="사용 대상")
        self.tree.heading("hotkey", text="단축키")
        self.tree.column("category", width=90, minwidth=80, stretch=False, anchor="w")
        self.tree.column("label", width=280, minwidth=180, stretch=True, anchor="w")
        self.tree.column("target", width=110, minwidth=90, stretch=False, anchor="center")
        self.tree.column("hotkey", width=130, minwidth=110, stretch=False, anchor="center")
        scrollbar = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-Button-1>", lambda _event: self.assign_selected())
        self.tree.bind("<Return>", lambda _event: self.assign_selected())
        self.tree.bind("<Delete>", lambda _event: self.clear_selected())

        command_row = ttk.Frame(body)
        command_row.pack(fill="x", pady=(10, 0))
        ttk.Label(command_row, textvariable=self.count_var, foreground="#2257a6").pack(side="left")
        ttk.Button(command_row, text="단축키 지정", command=self.assign_selected, takefocus=0).pack(side="right", padx=(6, 0))
        ttk.Button(command_row, text="선택 항목 해제", command=self.clear_selected, takefocus=0).pack(side="right", padx=(6, 0))
        ttk.Button(command_row, text="모두 해제", command=self.clear_all, takefocus=0).pack(side="right")

        footer = ttk.Frame(self.window, padding=(14, 0, 14, 14))
        footer.pack(fill="x")
        ttk.Button(footer, text="저장", command=self.save, takefocus=0).pack(side="right", padx=(6, 0))
        ttk.Button(footer, text="취소", command=self.close, takefocus=0).pack(side="right")

    def _position_window(self):
        self.window.update_idletasks()
        width = min(720, max(620, self.window.winfo_screenwidth() - 80))
        height = min(650, max(500, self.window.winfo_screenheight() - 120))
        try:
            parent_x = self.parent.winfo_rootx()
            parent_y = self.parent.winfo_rooty()
            parent_w = self.parent.winfo_width()
            parent_h = self.parent.winfo_height()
            x = parent_x + (parent_w - width) // 2
            y = parent_y + (parent_h - height) // 2
        except Exception:
            x = (self.window.winfo_screenwidth() - width) // 2
            y = (self.window.winfo_screenheight() - height) // 2
        x = max(0, min(x, self.window.winfo_screenwidth() - width))
        y = max(0, min(y, self.window.winfo_screenheight() - height))
        self.window.geometry(f"{width}x{height}+{x}+{y}")

    def _target_label(self, action: HotkeyAction) -> str:
        return " / ".join(MODE_LABELS.get(mode, mode) for mode in action.modes)

    def _matching_actions(self):
        query = self.search_var.get().strip().casefold()
        for action in self.actions:
            haystack = f"{action.category} {action.label} {self._target_label(action)}".casefold()
            if not query or query in haystack:
                yield action

    def _refresh_tree(self, select_action_id: str | None = None):
        previous = select_action_id or self._selected_action_id()
        self.tree.delete(*self.tree.get_children())
        for action in self._matching_actions():
            self.tree.insert(
                "",
                "end",
                iid=action.id,
                values=(action.category, action.label, self._target_label(action), self.bindings.get(action.id, "")),
            )
        if previous and self.tree.exists(previous):
            self.tree.selection_set(previous)
            self.tree.focus(previous)
            self.tree.see(previous)
        self.count_var.set(f"{len(self.bindings)}개 지정")

    def _selected_action_id(self) -> str | None:
        selection = self.tree.selection()
        return str(selection[0]) if selection else None

    def assign_selected(self):
        action_id = self._selected_action_id()
        if not action_id:
            messagebox.showinfo("단축키 설정", "먼저 기능을 선택하세요.", parent=self.window)
            return
        action = self.action_by_id[action_id]
        self._open_capture_window(action)

    def _open_capture_window(self, action: HotkeyAction):
        capture = tk.Toplevel(self.window)
        capture.title("단축키 입력")
        capture.configure(bg="#ffffff")
        capture.resizable(False, False)
        capture.transient(self.window)
        capture.grab_set()

        frame = ttk.Frame(capture, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=action.label, font=("맑은 고딕", 10, "bold")).pack(anchor="w")
        prompt_var = tk.StringVar(value="Ctrl, Alt, Shift 또는 Win과 다른 키를 함께 누르세요.")
        ttk.Label(frame, textvariable=prompt_var, foreground="#667085", wraplength=390).pack(anchor="w", pady=(5, 14))
        current_var = tk.StringVar(value=self.bindings.get(action.id, "키 입력 대기 중"))
        ttk.Label(frame, textvariable=current_var, font=("맑은 고딕", 14, "bold"), foreground="#2257a6").pack(pady=(4, 16))
        ttk.Button(frame, text="취소", command=capture.destroy, takefocus=0).pack(side="right")

        def handle_key(event):
            if event.keysym == "Escape":
                capture.destroy()
                return "break"
            hotkey = hotkey_from_tk_event(event.keycode, event.state, event.keysym)
            if not hotkey:
                prompt_var.set("보조키와 문자·숫자·기능키를 함께 눌러주세요.")
                return "break"

            duplicate_id = next(
                (item_id for item_id, value in self.bindings.items() if value == hotkey and item_id != action.id),
                None,
            )
            if duplicate_id:
                duplicate = self.action_by_id.get(duplicate_id)
                duplicate_label = duplicate.label if duplicate else duplicate_id
                move = messagebox.askyesno(
                    "단축키 중복",
                    f"{hotkey}은(는) '{duplicate_label}'에 지정되어 있습니다.\n\n기존 지정을 해제하고 옮길까요?",
                    parent=capture,
                )
                if not move:
                    return "break"
                self.bindings.pop(duplicate_id, None)

            self.bindings[action.id] = hotkey
            current_var.set(hotkey)
            self._refresh_tree(action.id)
            capture.after(100, capture.destroy)
            return "break"

        capture.bind("<KeyPress>", handle_key)
        capture.update_idletasks()
        width, height = 440, 190
        x = self.window.winfo_rootx() + (self.window.winfo_width() - width) // 2
        y = self.window.winfo_rooty() + (self.window.winfo_height() - height) // 2
        capture.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        capture.after(50, capture.focus_force)

    def clear_selected(self):
        action_id = self._selected_action_id()
        if not action_id:
            return
        self.bindings.pop(action_id, None)
        self._refresh_tree(action_id)

    def clear_all(self):
        if not self.bindings:
            return
        if not messagebox.askyesno("단축키 모두 해제", "지정한 전역 단축키를 모두 해제할까요?", parent=self.window):
            return
        self.bindings.clear()
        self._refresh_tree()

    def save(self):
        self.on_save(dict(self.bindings))
        self.saved = True
        self.window.destroy()

    def close(self):
        self.window.destroy()

    def _on_destroy(self, event):
        if event.widget is not self.window or self._closed:
            return
        self._closed = True
        self.on_close(self.saved)
