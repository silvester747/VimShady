from __future__ import annotations

import pyglet
import multiprocessing as mp
import time

from dataclasses import dataclass, field
from multiprocessing import Process, Pipe
from pathlib import Path
from pyglet.gl import *
from pyglet.graphics import Batch, Group
from pyglet.graphics.shader import Shader, ShaderProgram, ShaderException
from threading import Thread
from typing import List, Optional


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
        self.shader = None

    def on_draw(self):
        self.clear()
        if self.shader is not None:
            self.shader.group.viewport_resolution = vec2(*self.get_framebuffer_size())
            self.shader.draw()
        self.fps.draw()


class ShaderCanvas(object):
    def __init__(self, vertex_source, fragment_source, texture_dir):
        self.vertex_shader = Shader(vertex_source, "vertex")
        self.fragment_shader = Shader(fragment_source, "fragment")
        self.program = ShaderProgram(self.vertex_shader, self.fragment_shader)
        self.batch = Batch()
        self.group = ShaderGroup(self.program, texture_dir)

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
            pyglet.gl.GL_TRIANGLE_STRIP,
            batch=self.batch,
            group=self.group,
            **input_variables,
        )

    def draw(self):
        self.batch.draw()


@dataclass
class vec2(object):
    x: float = 0.0
    y: float = 0.0

    def uniform(self):
        return self.x, self.y


class ShaderGroup(Group):
    def __init__(self, program, texture_dir):
        super().__init__()
        self.program = program
        self.texture_dir = texture_dir

        self.start_time = time.monotonic()
        self.viewport_resolution = vec2()

        self.textures = {}
        self.load_textures()

    def set_texture_dir(self, texture_dir):
        self.texture_dir = texture_dir
        self.load_textures()

    def load_textures(self):
        for uniform in self.program.uniforms:
            if uniform.startswith("tex"):
                file = self.find_texture_file(uniform[3:])
                if file is None:
                    print(f"Cannot find texture for {uniform}")
                else:
                    # Manual loading into texture in order to set texture wrap settings
                    image = pyglet.image.load(file)
                    texture = pyglet.image.Texture.create(
                        image.width, image.height, GL_TEXTURE_2D, GL_SRGB8_ALPHA8
                    )
                    glBindTexture(texture.target, texture.id)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
                    image.blit_to_texture(texture.target, texture.level, 0, 0, 0, None)
                    glFlush()
                    self.textures[uniform] = texture

    def find_texture_file(self, name):
        found_files = list(self.texture_dir.glob(f"{name}.*", case_sensitive=False))
        if found_files:
            return found_files[0]
        return None

    def set_state(self):
        self.program.use()
        self.update_shadertoy_uniforms()
        self.update_bonzomatic_uniforms()

        for unit, uniform in enumerate(self.textures):
            self.textures[uniform].bind(texture_unit=unit)
            self.program[uniform] = unit

    def unset_state(self):
        self.program.stop()

    def update_shadertoy_uniforms(self):
        self.set_uniform("iTime", time.monotonic() - self.start_time)

    def update_bonzomatic_uniforms(self):
        self.set_uniform("fGlobalTime", time.monotonic() - self.start_time)
        self.set_uniform("v2Resolution", self.viewport_resolution.uniform())

    def set_uniform(self, name, value):
        if name in self.program.uniforms:
            self.program[name] = value


class RenderServer(object):
    def __init__(self, pipe):
        self.pipe = pipe
        self.window = RenderWindow()
        self.window.push_handlers(on_draw=self.handle_requests)

        self.texture_dir = Path(__file__).parent

        pyglet.app.run()

    def handle_requests(self):
        # Handle one request per frame for now
        if self.pipe.poll():
            request = self.pipe.recv()
            if isinstance(request, UpdateShaderRequest):
                self.handle_update_shader_request(request)
            elif isinstance(request, SetTextureDirRequest):
                self.handle_set_texture_dir_request(request)

    def handle_update_shader_request(self, request):
        try:
            new_shader = ShaderCanvas(
                DEFAULT_VERTEX_SOURCE, request.fragment_shader_source, self.texture_dir
            )
            self.window.shader = new_shader
            self.pipe.send(
                UpdateShaderResponse(
                    uniforms=UniformDetails.from_program(new_shader.program)
                )
            )
        except ShaderException as ex:
            self.pipe.send(UpdateShaderResponse(error=str(ex)))

    def handle_set_texture_dir_request(self, request):
        self.texture_dir = request.texture_dir
        try:
            if self.window.shader is not None:
                self.window.shader.group.set_texture_dir(self.texture_dir)
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
    except Exception as ex:
        print("Got an exception:")
        print(ex)
