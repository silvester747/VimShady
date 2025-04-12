# VimShady

Develop and test shaders from your favorite editor.

## Installation

### NeoVim with NvChad

1. Clone the repository.
2. Create a new python virtual environment using `python -m venv <VENVDIRNAME>`.
3. Activate the virtual environment.
4. Install required packages: `pip install neovim pynvim pyglet`.
5. Create the directory `rplugin/python3` in your NeoVim configuration directory.
6. Create a symlink `rplugin/python3/vimshady` to the `vimshady` directory in the git repository.
7. Add the following lines to `lua/custom/init.lua`:

```lua
vim.g.python3_host_prog = "<VENVDIRNAME>"

local enable_providers = {
      "python3_provider",
    }
for _, plugin in pairs(enable_providers) do
  vim.g["loaded_" .. plugin] = nil
  vim.cmd("runtime " .. plugin)
end

vim.cmd("runtime! plugin/rplugin.vim")
```

8. Start NeoVim.
9. Run `:UpdateRemotePlugins`.
10. Restart NeoVim.

