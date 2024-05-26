from __future__ import annotations

import pyglet
import multiprocessing as mp

from dataclasses import dataclass, field
from multiprocessing import Process, Pipe
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
        super().__init__(caption="Vim Shady")

        self.fps = pyglet.window.FPSDisplay(self)
        self.shader = None

    def on_draw(self):
        self.clear()
        if self.shader is not None:
            self.shader.draw()
        self.fps.draw()


class ShaderCanvas(object):
    def __init__(self, vertex_source, fragment_source):
        self.vertex_shader = Shader(vertex_source, "vertex")
        self.fragment_shader = Shader(fragment_source, "fragment")
        self.program = ShaderProgram(self.vertex_shader, self.fragment_shader)
        self.batch = Batch()
        self.group = ShaderGroup(self.program)
        self.vlist = self.program.vertex_list(
            4,
            pyglet.gl.GL_TRIANGLE_STRIP,
            batch=self.batch,
            group=self.group,
            in_pos=(
                "f",
                (-1.0, -1.0, 0.5, -1.0, 1.0, 0.5, 1.0, -1.0, 0.5, 1.0, 1.0, 0.5),
            ),
            in_texcoord=("f", (0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0)),
        )

    def draw(self):
        self.batch.draw()


class ShaderGroup(Group):
    def __init__(self, program):
        super().__init__()
        self.program = program

    def set_state(self):
        self.program.use()

    def unset_state(self):
        self.program.stop()


class RenderServer(object):
    def __init__(self, pipe):
        self.pipe = pipe
        self.window = RenderWindow()
        self.window.push_handlers(on_draw=self.handle_requests)
        pyglet.app.run()

    def handle_requests(self):
        # Handle one request per frame for now
        if self.pipe.poll():
            request = self.pipe.recv()
            if isinstance(request, UpdateShaderRequest):
                self.handle_update_shader_request(request)

    def handle_update_shader_request(self, request):
        try:
            new_shader = ShaderCanvas(
                DEFAULT_VERTEX_SOURCE, request.fragment_shader_source
            )
            self.window.shader = new_shader
            self.pipe.send(
                UpdateShaderResponse(
                    uniforms=UniformDetails.from_program(new_shader.program)
                )
            )
        except ShaderException as ex:
            self.pipe.send(UpdateShaderResponse(error=str(ex)))


class RenderClient(object):
    def __init__(self, process, pipe):
        self.pipe = pipe

    def update_shader_source(self, shader_source):
        self.pipe.send(UpdateShaderRequest(shader_source))
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

    fragment_source = """#version 410 core
        in vec4 out_texcoord;
        out vec4 out_color;

        uniform vec2 test;

        void main()
        {
            out_color = vec4(1., out_texcoord.y, 0., test.y);
        }
    """
    try:
        response = client.update_shader_source(fragment_source)
        print(f"Detected uniforms: {', '.join(str(u) for u in response.uniforms)}")
    except Exception as ex:
        print("Got an exception:")
        print(ex)
