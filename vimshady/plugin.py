import pynvim

from threading import Thread

from .renderer import start_render_server


@pynvim.plugin
class VimShadyPlugin(object):
    def __init__(self, nvim):
        self.nvim = nvim
        self.logger = None
        self.render_client = None
        self.attached_buffer = None
        self.auto_command_group = None

    @pynvim.command("VimShady")
    def vim_shady(self):
        """Start/stop a shader window for the current buffer"""
        if self._is_current_buffer_attached():
            self._detach_from_current_buffer()
        else:
            self._attach_to_current_buffer()

    @pynvim.command("VimShadyUpdateShader")
    def update_shader(self):
        """Update the shader from the current buffer"""
        self._update_shader()

    def _attach_to_current_buffer(self):
        self._delete_auto_commands()
        self.attached_buffer = self.nvim.current.buffer
        self.logger = LogWindow(self.nvim)
        if self.render_client is None:
            self.render_client = start_render_server()
        self.logger.append(f"Rendering shader from `{self.nvim.current.buffer.name}`")
        self._update_shader()
        self._create_auto_commands()

    def _detach_from_current_buffer(self):
        self._delete_auto_commands()
        self.attached_buffer = None
        self.logger.close()
        self.render_client = None

    def _create_auto_commands(self):
        self.auto_command_group = self.nvim.api.create_augroup("VimShadyAUG", {})

        # Update shader on Buffer Write:
        self.nvim.api.create_autocmd(
            "BufWrite",
            {
                "group": self.auto_command_group,
                "buffer": self.attached_buffer.number,
                "command": ":VimShadyUpdateShader",
            },
        )

    def _delete_auto_commands(self):
        if self.auto_command_group is not None:
            self.nvim.api.del_augroup_by_id(self.auto_command_group)
            self.auto_command_group = None

    def _update_shader(self):
        try:
            fragment_source = "\n".join(self.attached_buffer)
            result = self.render_client.update_shader_source(fragment_source)
            self.logger.append("Shader compiled")
            if result.uniforms:
                self.logger.append("Uniforms detected:")
                for u in result.uniforms:
                    self.logger.append(f"\t{u.name}: length={u.length}, size={u.size}")
        except Exception as ex:
            self.logger.append(*str(ex).split("\n"))

    def _is_current_buffer_attached(self):
        return self.attached_buffer is not None and self.nvim.current.buffer.number == self.attached_buffer.number


class LogWindow(object):
    def __init__(self, nvim):
        self.nvim = nvim

        self.buffer = None
        self.window = None

        self._ensure_buffer()
        self._ensure_window()

    def append(self, *text):
        self._ensure_buffer()
        self._ensure_window()

        self.buffer.api.set_option("modifiable", True)
        self.buffer.append(text)
        self.buffer.api.set_option("modifiable", False)
        self.buffer.api.set_option("modified", False)
        self.window.api.set_cursor((len(self.buffer), 0))

    def close(self):
        if self.window is not None:
            if self.window.valid:
                self.window.api.close(True)
            self.window = None
        if self.buffer is not None:
            if self.buffer.valid:
                self.buffer.api.delete({"force": True})
            self.buffer = None

    def _ensure_buffer(self):
        if self.buffer is None or not self.buffer.valid:
            self.buffer = self.nvim.api.create_buf(False, True)
            if not self.buffer.valid:
                raise Exception("Could not create log buffer")
            self.buffer.api.set_option("modifiable", False)
            self.buffer.api.set_option("modified", False)

            self.window = None

    def _ensure_window(self):
        if (
            self.window is None
            or not self.window.valid
            or self.window.buffer.number != self.buffer.number
        ):
            self.window = self.nvim.api.open_win(
                self.buffer,
                False,
                {
                    "split": "below",
                    "height": 10,
                    "style": "minimal",
                },
            )
            if not self.window.valid:
                raise Exception("Could not create log window")
