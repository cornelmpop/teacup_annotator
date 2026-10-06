"""Install Tk input bindings on a completed application window."""

from __future__ import annotations

from functools import partial
import sys
from typing import cast

from annotator.gui.canvas_render import CanvasRenderHost
from annotator.gui.canvas_render import on_canvas_configure
from annotator.gui.input.keyboard import on_key_press
from annotator.gui.input.keyboard import on_key_release
from annotator.gui.input.pointer_drag import on_left_drag
from annotator.gui.input.pointer_drag import on_left_release
from annotator.gui.input.pointer_drag import on_right_drag
from annotator.gui.input.pointer_drag import on_right_release
from annotator.gui.input.pointer_menu import on_middle_press
from annotator.gui.input.pointer_menu import on_right_press
from annotator.gui.input.pointer_motion import on_mouse_leave
from annotator.gui.input.pointer_motion import on_mouse_motion
from annotator.gui.input.pointer_motion import on_mouse_wheel
from annotator.gui.input.pointer_primary import on_left_press
from annotator.gui.input.state import InputBindingHost
from annotator.gui.interactions import bind_canvas_wheel
from annotator.gui.window.state import WindowWidgets

# CMP: QUESTION - Why does MacOS require this mapping? Does it
#      reflect my specific machine situation? This brings up a
#      bigger issue. Should these be configurable instead of hard
#      coded here?
def bind_window_events(
    host: InputBindingHost,
    widgets: WindowWidgets,
) -> None:
    """Bind mouse, canvas, wheel, and keyboard callbacks to the host."""

    canvas = widgets.viewer.canvas
    canvas.bind("<ButtonPress-1>", partial(on_left_press, host))
    canvas.bind("<B1-Motion>", partial(on_left_drag, host))
    canvas.bind("<ButtonRelease-1>", partial(on_left_release, host))
    if sys.platform == "darwin":
        canvas.bind("<ButtonPress-2>", partial(on_right_press, host))
        canvas.bind("<B2-Motion>", partial(on_right_drag, host))
        canvas.bind("<ButtonRelease-2>", partial(on_right_release, host))
        canvas.bind("<ButtonPress-3>", partial(on_middle_press, host))
    else:
        canvas.bind("<ButtonPress-2>", partial(on_middle_press, host))
        canvas.bind("<ButtonPress-3>", partial(on_right_press, host))
        canvas.bind("<B3-Motion>", partial(on_right_drag, host))
        canvas.bind("<ButtonRelease-3>", partial(on_right_release, host))
    canvas.bind("<Control-ButtonPress-1>", partial(on_right_press, host))
    canvas.bind(
        "<Configure>",
        partial(on_canvas_configure, cast(CanvasRenderHost, host)),
    )
    canvas.bind("<Motion>", partial(on_mouse_motion, host))
    canvas.bind("<Leave>", partial(on_mouse_leave, host))
    bind_canvas_wheel(canvas, partial(on_mouse_wheel, host))
    host.root.bind_all("<KeyPress>", partial(on_key_press, host))
    host.root.bind_all("<KeyRelease>", partial(on_key_release, host))
