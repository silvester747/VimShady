from __future__ import annotations

import multiprocessing as mp
import time
from dataclasses import astuple, dataclass, field
from pathlib import Path
from typing import List, Optional

import pyglet
import pyglet.gl as gl
from pyglet.graphics import Batch, Group
from pyglet.graphics.shader import Shader, ShaderException, ShaderProgram
from pyglet.window import key

from .config import Config

DEFAULT_VERTEX_SOURCE = """#version 410 core
    in vec3 in_pos;
    in vec2 in_texcoord;
    out vec2 out_texcoord;

    void main()
    {
        gl_Position = vec4(in_pos, 1.0);
        out_texcoord = in_texcoord;
    }
"""


class RenderWindow(pyglet.window.Window):
    def __init__(self):
        super().__init__(caption="Vim Shady", resizable=True)

        self.fps = pyglet.window.FPSDisplay(self)
        self.timer = Timer()
        self.uniform_data = UniformData()
        self.shader = None

        self.info_label = pyglet.text.Label(
            "Starting",
            font_size=24,
            color=(127, 127, 127, 127),
            x=self.width - 10,
            y=0,
            anchor_x="right",
            anchor_y="bottom",
        )
        self._update_info_label()

        config = Config.load()
        self.set_location(config.window_x, config.window_y)
        self.set_size(config.window_width, config.window_height)

    def load_shader(self, fragment_shader_source, texture_dir):
        new_shader = ShaderCanvas(
            DEFAULT_VERTEX_SOURCE,
            fragment_shader_source,
            texture_dir,
            self.uniform_data,
        )
        self.shader = new_shader
        return new_shader.program

    def on_draw(self):
        self.clear()
        if self.shader is not None:
            self.uniform_data.timer_tick = self.timer.tick()
            self.shader.draw()
        self.fps.draw()
        self.info_label.draw()

    def on_key_press(self, symbol, modifiers):
        if symbol == key.P:
            self.timer.running = not self.timer.running
        elif symbol in (key.MINUS, key.UNDERSCORE):
            if modifiers & key.MOD_CTRL:
                self.timer.speed -= 1.0
            elif modifiers & key.MOD_SHIFT:
                self.timer.speed -= 0.5
            else:
                self.timer.speed -= 0.1
        elif symbol in (key.EQUAL, key.PLUS):
            if modifiers & key.MOD_CTRL:
                self.timer.speed += 1.0
            elif modifiers & key.MOD_SHIFT:
                self.timer.speed += 0.5
            else:
                self.timer.speed += 0.1
        elif symbol == key.Q:
            self.on_close()

        self._update_info_label()

    def on_mouse_press(self, x, y, button, modifiers):
        self.uniform_data.mouse_click(x, y)

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        self.uniform_data.mouse_move(x, y, dx, dy)

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        self.uniform_data.mouse_scroll(scroll_x, scroll_y)

    def on_resize(self, width, height):
        super().on_resize(width, height)
        self.info_label.x = width - 10
        self.uniform_data.window_resize(*self.get_framebuffer_size())

    def on_show(self):
        size = self.get_framebuffer_size()
        self.uniform_data.window_resize(*size)
        self.uniform_data.mouse_click(size[0] / 2, size[1] / 2)

    def on_close(self):
        config = Config.load()
        config.window_x, config.window_y = self.get_location()
        config.window_width, config.window_height = self.get_size()
        config.save()
        super().on_close()

    def _update_info_label(self):
        speed = f"{self.timer.speed:.1f}" if self.timer.running else "Paused"
        self.info_label.text = f"Speed: {speed}"


class Timer(object):
    def __init__(self):
        self.running = True
        self.speed = 1.0

        self._total_time = 0.0
        self._start_time = time.monotonic()
        self._last_frame_time = self._start_time

    def tick(self):
        now = time.monotonic()
        if self.running:
            diff = now - self._last_frame_time
            self._total_time += diff * self.speed
        else:
            diff = 0.0

        self._last_frame_time = now
        return TimerTick(self._total_time, diff)


@dataclass
class TimerTick(object):
    total_time: int
    frame_time: int


class ShaderCanvas(object):
    def __init__(self, vertex_source, fragment_source, texture_dir, uniform_data):
        self.vertex_shader = Shader(vertex_source, "vertex")
        self.fragment_shader = Shader(fragment_source, "fragment")
        self.program = ShaderProgram(self.vertex_shader, self.fragment_shader)
        self.batch = Batch()
        self.texture_loader = TextureLoader(self.program, texture_dir)
        self.group = ShaderGroup(self.program, self.texture_loader, uniform_data)

        input_variables = {}
        if "in_pos" in self.program.attributes:
            input_variables["in_pos"] = (
                "f",
                (-1.0, -1.0, 0.5, -1.0, 1.0, 0.5, 1.0, -1.0, 0.5, 1.0, 1.0, 0.5),
            )
        if "in_texcoord" in self.program.attributes:
            input_variables["in_texcoord"] = (
                "f",
                (0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0),
            )

        self.vlist = self.program.vertex_list(
            4,
            gl.GL_TRIANGLE_STRIP,
            batch=self.batch,
            group=self.group,
            **input_variables,
        )

    def draw(self):
        self.batch.draw()


class TextureLoader(object):
    def __init__(self, program, texture_dir):
        self.program = program
        self.textures = {}
        self._texture_dir = texture_dir
        self._load_textures()

    @property
    def texture_dir(self):
        return self._texture_dir

    @texture_dir.setter
    def texture_dir(self, value):
        self._texture_dir = value
        self._load_textures()

    def bind(self):
        for unit, uniform in enumerate(self.textures):
            self.textures[uniform].bind(texture_unit=unit)
            self.program[uniform] = unit

    def _load_textures(self):
        for uniform in self.program.uniforms:
            if uniform.startswith("tex"):
                file = self._find_texture_file(uniform[3:])
                if file is None:
                    print(f"Cannot find texture for {uniform}")
                else:
                    # Manual loading into texture in order to set texture wrap settings
                    image = pyglet.image.load(file)
                    texture = pyglet.image.Texture.create(
                        image.width, image.height, gl.GL_TEXTURE_2D, gl.GL_SRGB8_ALPHA8
                    )
                    gl.glBindTexture(texture.target, texture.id)
                    gl.glTexParameteri(
                        gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_REPEAT
                    )
                    gl.glTexParameteri(
                        gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_REPEAT
                    )
                    image.blit_to_texture(texture.target, texture.level, 0, 0, 0, None)
                    gl.glFlush()
                    self.textures[uniform] = texture

    def _find_texture_file(self, name):
        found_files = list(self.texture_dir.glob(f"{name}.*", case_sensitive=False))
        if found_files:
            return found_files[0]
        return None


@dataclass
class vec2:
    x: float = 0.0
    y: float = 0.0


@dataclass
class ivec2:
    x: int = 0
    y: int = 0


class UniformData(object):
    def __init__(self):
        self.timer_tick = TimerTick(0.0, 0.0)
        self._viewport_resolution = ivec2()
        self._mouse_current = ivec2()
        self._mouse_click = ivec2()
        self._mouse_scroll = vec2()

    def mouse_click(self, x, y):
        self._mouse_current = ivec2(x, y)
        self._mouse_click = ivec2(x, y)

    def mouse_move(self, x, y, dx, dy):
        self._mouse_current = ivec2(x, y)

    def mouse_scroll(self, scroll_x, scroll_y):
        self._mouse_scroll.x += scroll_x
        self._mouse_scroll.y += scroll_y

    def window_resize(self, width: int, height: int):
        self._viewport_resolution = ivec2(width, height)

    def update(self, program):
        self._update_shadertoy_uniforms(program)
        self._update_bonzomatic_uniforms(program)
        self._update_vimshady_uniforms(program)

    def _update_shadertoy_uniforms(self, program):
        self._set_uniform(program, "iTime", self.timer_tick.total_time)
        self._set_uniform(program, "iTimeDelta", self.timer_tick.frame_time)
        self._set_uniform(
            program, "iMouse", astuple(self._mouse_current) + astuple(self._mouse_click)
        )

    def _update_bonzomatic_uniforms(self, program):
        self._set_uniform(program, "fGlobalTime", self.timer_tick.total_time)
        self._set_uniform(program, "fFrameTime", self.timer_tick.frame_time)
        self._set_uniform(program, "v2Resolution", astuple(self._viewport_resolution))

    def _update_vimshady_uniforms(self, program):
        self._set_uniform(program, "iMouseScroll", astuple(self._mouse_scroll))

    def _set_uniform(self, program, name, value):
        if name in program.uniforms:
            program[name] = value


class ShaderGroup(Group):
    def __init__(self, program, texture_loader, uniform_data):
        super().__init__()
        self.program = program
        self.texture_loader = texture_loader
        self.uniform_data = uniform_data

    def set_state(self):
        self.program.use()
        self.texture_loader.bind()
        self.uniform_data.update(self.program)

    def unset_state(self):
        self.program.stop()


class RenderServer(object):
    def __init__(self, pipe):
        self.pipe = pipe
        self.window = RenderWindow()
        self.window.push_handlers(on_draw=self._handle_requests)

        self.texture_dir = Path(__file__).parent

        pyglet.app.run()

    def _handle_requests(self):
        # Handle one request per frame for now
        if self.pipe.poll():
            request = self.pipe.recv()
            if isinstance(request, UpdateShaderRequest):
                self._handle_update_shader_request(request)
            elif isinstance(request, SetTextureDirRequest):
                self._handle_set_texture_dir_request(request)

    def _handle_update_shader_request(self, request):
        try:
            program = self.window.load_shader(
                request.fragment_shader_source, self.texture_dir
            )
            self.pipe.send(
                UpdateShaderResponse(uniforms=UniformDetails.from_program(program))
            )
        except ShaderException as ex:
            self.pipe.send(UpdateShaderResponse(error=str(ex)))

    def _handle_set_texture_dir_request(self, request):
        self.texture_dir = request.texture_dir
        try:
            if self.window.shader is not None:
                self.window.shader.texture_loader.texture_dir = self.texture_dir
            self.pipe.send(SetTextureDirResponse())
        except Exception as ex:
            self.pipe.send(SetTextureDirResponse(error=str(ex)))


class RenderClient(object):
    def __init__(self, process, pipe):
        self.pipe = pipe

    def update_shader_source(self, shader_source):
        self.pipe.send(UpdateShaderRequest(shader_source))
        response = self.pipe.recv()
        if response.error is not None:
            raise Exception(response.error)
        return response

    def set_texture_dir(self, texture_dir):
        self.pipe.send(SetTextureDirRequest(texture_dir))
        response = self.pipe.recv()
        if response.error is not None:
            raise Exception(response.error)
        return response


@dataclass
class UpdateShaderRequest(object):
    fragment_shader_source: str


@dataclass
class UpdateShaderResponse(object):
    error: Optional[str] = None
    uniforms: List[UniformDetails] = field(default_factory=list)


@dataclass
class SetTextureDirRequest(object):
    texture_dir: Path


@dataclass
class SetTextureDirResponse(object):
    error: Optional[str] = None


@dataclass
class UniformDetails(object):
    name: str
    length: int
    location: int
    size: int

    @classmethod
    def from_program(cls, program):
        return [
            cls(
                name=key,
                length=value["length"],
                location=value["location"],
                size=value["size"],
            )
            for key, value in program.uniforms.items()
        ]


def start_render_server():
    ctx = mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe()
    process = ctx.Process(target=RenderServer, args=(child_conn,))
    process.start()
    return RenderClient(process, parent_conn)


if __name__ == "__main__":
    client = start_render_server()

    test_data_dir = Path(__file__).parent.with_name("test")

    fragment_source = (test_data_dir / "test.glsl").read_text()
    try:
        response = client.update_shader_source(fragment_source)
        print(f"Detected uniforms: {', '.join(str(u) for u in response.uniforms)}")
        client.set_texture_dir(test_data_dir)
        response = client.update_shader_source(fragment_source)
    except Exception as ex:
        print("Got an exception:")
        print(ex)
