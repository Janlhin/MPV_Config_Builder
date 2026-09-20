-- 临时脚本：把 mpv 的内置按键绑定导出成 JSON
-- 用法：mpv.com --no-config --idle --vo=null --ao=null --script=这个文件.lua
-- 输出路径从环境变量 MPV_KEYS_OUT 读，没设就写 ./mpv_bindings.json

local mp = require 'mp'
local utils = require 'mp.utils'

local out = os.getenv('MPV_KEYS_OUT') or 'mpv_bindings.json'

mp.add_timeout(0.3, function()
    local ok, bindings = pcall(function() return mp.get_property_native('input-bindings') end)
    local ok2, commands = pcall(function() return mp.get_property_native('input-commands') end)
    local f = io.open(out, 'w')
    if not f then
        mp.command('quit')
        return
    end
    f:write(utils.format_json({
        bindings = ok and bindings or {},
        commands = ok2 and commands or {},
    }))
    f:close()
    mp.command('quit')
end)
