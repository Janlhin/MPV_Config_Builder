# An Introduction to MPV Configuration · From "Where to Put the Files" to "How to Recover if You Break It"

This is for people who are encountering MPV configuration for the first time. After reading this, you will at least be able to do three things:
**know where to put the files**, **understand what a configuration snippet is saying**, and **revert your changes if you break something**.

> The path rules, syntax, and meaning of `~~/` in this article all come from the official MPV manual (the Chinese version, mpv_doc-CN).
> These are not just tips based on experience. I have tried to mark every place where the manual states something explicitly.

---

## 1. Where Exactly Should mpv.conf Be Placed?

MPV will only read configuration from **one** "configuration directory". Where this directory is located depends on three different situations:

| Situation | Set Directory | Description |
|---|---|---|
| **Portable Version** (Recommended) | `portable_config\` next to `mpv.exe` | Original manual text: "If a directory named `portable_config` exists next to mpv.exe, all settings will be loaded only from this directory." watch-later and cache are also written here; copy the entire folder to switch machines. |
| **Default Installation** (Windows) | `%APPDATA%\mpv\` | Usually `C:\users\your_username\AppData\Roaming\mpv\`, and the configuration is the `mpv.conf` file here |
| **Specify yourself** | Any directory | Add `--config-dir="D:\myconf"` to the startup parameters, or use the environment variable `MPV_HOME` |

**How to check which type you belong to?** Run a single command in cmd to see what the default path looks like:

```bat
echo %APPDATA%\mpv\mpv.conf
```

Then take another look to see if there's a `portable_config` folder next to `mpv.exe` — **if there is, it's the portable version, and you can ignore the one in `%APPDATA%`**.

### Which type is mpv-lazy?

mpv-lazy is the **portable version**. Everything you need to modify is located in:

```
mpv-lazy\
├─ mpv.exe
└─ portable_config\          ← This is the "Settings Directory"
   ├─ mpv.conf               ← Main configuration file; modify this one
   ├─ input.conf             ← Keyboard shortcuts
   ├─ profiles.conf          ← Conditional configurations (in [section] format; see Section 5)
   ├─ script-opts.conf       ← Script parameters

├─ scripts\               ← Place .lua / .js scripts here
├─ shaders\               ← Place .glsl / .hook shaders here
├─ vs\                    ← Place .vpy frame interpolation/super-resolution scripts here
├─ fonts\                 ← Place subtitle fonts here

└─ watch_later\           ← Playback progress memory (auto-generated)
```

**Just remember one thing**: `portable_config\` is the "home" of this mpv; configurations, scripts, shaders, and fonts are all stored here.

---

## 2. What is `~~/`? Why do we see it everywhere?

`~~/` is a **shorthand for the "settings directory"**. The original manual text says: `~~/` will return the path that **exists** under the settings directory.

| Notation | Points to |
|---|---|
| `~~/shaders/FSRCNNX.glsl` | `portable_config\shaders\FSRCNNX.glsl` |
| `~~/vs/MEMC_RIFE_NV.vpy` | `portable_config\vs\MEMC_RIFE_NV.vpy` |
| `~~/fonts` | `portable_config\fonts` |
| `~~desktop/` | Your desktop (screenshots often use `~~desktop/`) |
| `~~exe_dir/` | Directory where `mpv.exe` is located |

**Why use this instead of writing `C:\Program Files\mpv-lazy\...`?**
Because if you change the drive, the username, or move the entire folder, `~~/` will still work, whereas absolute paths will become completely useless.
So when copying someone else's configuration, if you see `~~/`, just copy it as-is. If you see `C:\Users\SomeName\...`, be sure to change it to your own path.

---

## 3. How to Write the Configuration: 5 Rules

**1. One option per line, written as `key=value`. Do not use `--`.**

```ini
vo=gpu-next          ✅
--vo=gpu-next        ❌（`--` is for the command line; do not include it in the configuration file）
```

**2. Everything after `#` is a comment** (Manual original: "Everything after `#` is considered a comment")

```ini
# Full-line comment
vo=gpu-next   # A trailing-line comment is also possible
```

⚠️ **There's a major pitfall here**: since everything after `#` is treated as a comment, **color values must be enclosed in quotes**, otherwise they will be truncated:

```ini
sub-color=#FFD766          ❌ The actual effective value is empty (the part after # is treated as a comment)
sub-color="#FFD766"        ✅
```

**3. Just writing an option name = enables it** (Manual: "If this value is omitted, it implies yes")

```ini
hwdec          ←  equals hwdec=yes
```

**4. Add quotes if the value contains special characters**

Spaces, `#`, `"`, `'`, `%`, as well as any leading or trailing spaces, must all be enclosed in quotes:

```ini
osd-playing-msg="File: ${filename}"
screenshot-directory="~~desktop/My Screenshots"
```

5. Use semicolons `;` to separate list items; never use colons on Windows.

```ini
glsl-shaders="~~/shaders/a.glsl;~~/shaders/b.glsl"     ✅
glsl-shaders="C:/shaders/a.glsl"                        ✅ (single path, enclosed in quotes)
glsl-shaders="C:/a.glsl:C:/b.glsl"                      ❌ The colon will conflict with the drive letter
```

## 4. How to make changes take effect and confirm they have

**Configuration is only read once when MPV starts** — after making changes, you must **restart MPV** (not just restart the video; quit and reopen it).

To see "whether the changes actually took effect":

1. While playing, press `i`, then press `2` → this opens the stats panel, where you can see the current resolution, frame rate, dropped frames,
   and **Render Time**. Use this to determine whether the configuration is manageable; don't just guess.
2. To see which files MPV actually read and whether any errors occurred, add `--log-file=%TEMP%\mpv.log` to the startup parameters,
   then open this log file and search for `mpv.conf`.

**Priority** (from the original manual): system-wide < user-level/portable configuration < command line.
Therefore, to temporarily test a parameter, simply add it directly on the command line — no need to modify any files:

```bat
mpv.exe --vo=gpu-next "D:\video.mkv"
```

## 5. `[Subsection]` is conditional configuration; don't copy it as global configuration.

In `profiles.conf` or `mpv.conf`, you might see a syntax like this:

```ini
[ontop_playback]
profile-desc=Always on top during playback
profile-cond=not pause and not p.idle_active
ontop=yes
```

The `[name]` is called **profile**, and the options within it **only take effect when conditions are met** (the item above is an example of "keep window on top while playing").

⚠️ The most common mistake made by beginners: **copying options from a subsection to the global settings**, which turns something that "was originally only supposed to take effect under certain conditions" into a permanent setting.
When this tool reads the configuration, it will list the profile separately and will not mix it with global values. To use a specific profile, you must select it manually, and you will be reminded of the consequences.

---

## 6. How to recover if something goes wrong (three fallback options, from least to most drastic)

| Method | How to do it | Suitable for |
|---|---|---|
| **Comment it out** | Add `#` before that line and restart mpv | Only a specific option is problematic |
| **Restore from a backup** | Find a file like `mpv.conf.bak-20260913-171205` in the same directory, rename it to `mpv.conf` to overwrite | Changes have gone wrong and you want to roll everything back |
| **Delete the config and start over** | Delete `mpv.conf` (or rename it to `mpv.conf.old`); mpv will start with default values | You have no idea what went wrong |

**Who generates the backups?** This tool automatically generates a `filename.bak-timestamp` before each write.
On the full version's "Versions / Rollback" page, you can roll back with a single click (it will back up the current version again before rolling back).

**Uninstalling configurations written with this tool is even simpler**: By default, it uses the "standalone include file" method —
it generates an `mpv-builder.conf` and adds a line to your `mpv.conf`:
`include = "~~/mpv-builder.conf"`. To undo everything: **delete `mpv-builder.conf` and remove that include line**. Not a single character of your original configuration will be altered.

---

## 7. The 8 Most Common Pitfalls for Beginners

1. **Path not enclosed in quotes** — Paths containing spaces or `#` will be truncated or cause an error.
2. **Shader list separated by colons** — On Windows, colons are used for drive letters, and mpv will misread them. Use `;` instead.
3. **File saved as UTF-16 or with a BOM** — Some editors use this as the default, and mpv will read extra, strange characters in the key names.
   Saving as **UTF-8 without a BOM** is the safest option (GBK can also be read, but mixing encodings can easily cause issues).
4. **Configuration copied but not the files** — The configuration specifies `~~/shaders/xxx.glsl`, but the file is not present in your `shaders\` directory.
   This will result in no effect at best, or a black screen at worst. This tool will clearly tell you: "Missing locally: xxx".
5. **Loading two vpy scripts at the same time** — mpv can only have one `vf=vapoursynth=` active at any given moment.

To make "frame interpolation + super-resolution" take effect simultaneously, you can only use "multi-script fusion" to merge the two scripts into a single `.vpy` file.
6. **Stacking two super-resolution passes** — if the shader chain includes two super-resolution families like FSRCNNX and Anime4K Upscale at the same time,
   the load doubles, and ringing artifacts are likely to occur. Choosing one family is sufficient.
7. **`interpolation=yes` paired with a non-display sync mode** — the manual explicitly states that interpolation will be **silently disabled** in this case,
   so what you see is "enabled but ineffective." You should use `video-sync=display-resample` instead.
8. **Unable to modify configuration after installing to `Program Files`** — that directory requires administrator permissions. Either run the program as an administrator,

Either install mpv to the user directory (this tool installs mpv-lazy to `%LOCALAPPDATA%\mpv-lazy` by default, no admin rights required).

---

## 8. Starting from Scratch: Recommended Order

1. **Don't write any configuration yet**. Play a video you're most familiar with using the default settings, press `i` then `2`, and take a look at the Render Time and dropped frames.
2. **Install a portable version** (mpv-lazy is a good choice) and note down the configuration directory.
3. **Try changing only 3 options** to test the waters:

   ```ini
   vo=gpu-next             # Use the new GPU renderer (the default gpu is also fine)
   hwdec=auto-safe         # Enable hardware decoding, which greatly reduces CPU load
   scale=spline36          # Upscaling algorithm, better than the default bilinear, with low performance requirements
   
   ```

After making changes, restart mpv, then press `i`/`2` to compare the Render Time.
4. **Only add more once you're sure everything is fine** — scaling algorithm → debanding → shader → frame interpolation. Add only one type at a time.
5. **Keep a backup after each step** (or just use this tool to write it, as it will create backups automatically).

---

## 9. What tasks can this tool save you from?

| What you want to do | Which page to use | What it does for you |
|---|---|---|
| I don't want to understand those parameters at all | **Basic Mode** | Ask 4 questions to directly generate a set of configurations |
| Want to adjust but are afraid of messing it up | **Advanced Mode** | 6 preset sets + 9 one-click combinations; tick to preview; an invalid value is blocked immediately with a red box, and **the wrong value is never written** |
| Want to go all the way | **The Complete Edition** | All 829 mpv options are included, with Chinese descriptions, types, default values, and value ranges |
| Just want to check if there's anything wrong with the current configuration | **Configuration Health Check** | Drag a `mpv.conf` file in: encoding, include chains, profiles, unknown options, duplicates, and compatibility conflicts—all listed at once |
| Want to do "Frame Interpolation + Super-Resolution" together | **Advanced Mode → Frame Interpolation Script → Multi-Script Fusion** | Synthesize a `.vpy` by following "Deinterlace → Denoise → Super-Resolution → Frame Interpolation"; the original script remains unchanged, and perform a syntax check before generation |
| Want to write it from scratch yourself | **Hell Mode** | A text box, no restrictions; a `.bak` file is still saved before writing |

**What this tool does not do** (to avoid any misunderstandings):

- It **does not play videos**; it only ensures the configuration is written correctly.
- By default, it **does not modify the contents of your `mpv.conf`**, but simply adds an `include` line pointing to the file it generates (to uninstall, just delete the file and that line).
- It **does not connect to the internet** (except when you click on download links yourself); all configuration analysis is done locally.
- It **does not bundle mpv or any third-party files**; all download links point to official release pages.

---

## Appendix: Three Minimal Usable Configurations

**Integrated Graphics Laptop (Power Saving Priority)**

```ini
vo=gpu-next
hwdec=auto-safe
video-sync=audio
scale=bilinear
cscale=bilinear
dscale=bilinear
```

**Desktop with Dedicated GPU (Graphics Quality Priority)**

```ini
vo=gpu-next
gpu-api=d3d11
hwdec=auto-safe
video-sync=display-resample
scale=ewa_lanczossharp
cscale=ewa_lanczossharp
dscale=hermite
sigmoid-upscaling=yes
deband=yes
deband-iterations=2
```

**Added shaders and frame interpolation (the corresponding files must actually exist)**

```ini
vo=gpu-next
hwdec=auto-safe
video-sync=display-resample
scale=ewa_lanczossharp
cscale=ewa_lanczossharp
glsl-shaders="~~/shaders/FSRCNNX/FSRCNNX_x2_16_0_4_1.glsl;~~/shaders/Adaptive_sharpen/Adaptive_sharpen_lite_RT.glsl"
vf=vapoursynth="~~/vs/MEMC_RIFE_NV.vpy"
```

> Don't just copy the last one — the shader filenames and vpy script names are different in every version.
> Use "Advanced Mode → Scan and Download" to see which files you actually have on your machine, then choose.

---

**Related Documentation**: `MPV Shader Guide` (how to get the sharpest picture), `Acknowledgments and Licenses` (whose work this uses).
**Official Sources**: [mpv official manual](https://mpv.io/manual/master/) · [mpv_doc-CN Chinese manual](https://github.com/hooke007/mpv_doc-CN) ·
[mpv-lazy / mpv_PlayKit](https://github.com/hooke007/mpv_PlayKit)
