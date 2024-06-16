    #version 410 core

    in vec4 out_texcoord;
    out vec4 out_color;

    uniform float fGlobalTime;
    uniform vec2 test;
    uniform sampler2D texNoise;
    uniform vec4 iMouse;

    void main()
    {
      out_color = vec4(.5 + .5*sin(fGlobalTime), out_texcoord.y, 0., test.y);
      out_color += texture(texNoise, out_texcoord.xy);

      if (length(gl_FragCoord.xy - iMouse.xy) < 20.) {
        out_color = vec4(0.);
      }
      if (length(gl_FragCoord.xy - iMouse.zw) < 20.) {
        out_color = vec4(1.);
      }
    }
