import pynvim

from threading import Thread

from .renderer import start_render_server

@pynvim.plugin
class VimShadyPlugin(object):
    def __init__(self, nvim):
        self.nvim = nvim
        self.logger = None
        self.render_client = None

    @pynvim.command("VimShady")
    def vim_shady(self):
        """Start a shader window for the current buffer"""
        self.logger = LogWindow(self.nvim)
        self.render_client = start_render_server()
        self.update_shader()

    def update_shader(self):
        try:
            fragment_source = "\n".join(self.nvim.current.buffer)
            self.render_client.update_shader_source(fragment_source)
            self.logger.append("Shader compiled")
        except Exception as ex:
            self.logger.append(*str(ex).split("\n"))


class LogWindow(object):
    def __init__(self, nvim):
        self.nvim = nvim

        self.buffer = self.nvim.api.create_buf(False, True)
        if not self.buffer.valid:
            raise Exception("Could not create log buffer")
        self.buffer.api.set_option("modifiable", False)
        self.buffer.api.set_option("modified", False)

        self.win = self.nvim.api.open_win(self.buffer, False, {
            "split": "below",
            "height": 10,
            "style": "minimal",
        })
        if not self.win.valid:
            raise Exception("Could not create log window")

    def append(self, text):
        self.nvim.async_call(self._append, text)

    def _append(self, *text):
        if not self.win.valid or not self.buffer.valid:
            raise Exception("Log window/buffer no longer valid")
        self.buffer.api.set_option("modifiable", True)
        self.buffer.append(text)
        self.buffer.api.set_option("modifiable", False)
        self.buffer.api.set_option("modified", False)
        self.win.api.set_cursor((len(self.buffer), 0))
