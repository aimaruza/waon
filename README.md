<p align="center">
  <img src="waon/assets/logo/logo.svg" alt="waon logo" width="96">
</p>

<h1 align="center">waon</h1>

<p align="center">A music organizer and audio player.</p>

> [!WARNING]
> **waon is in beta.** You might encounter some bugs, so keep
> a backup of anything you can't afford to lose. Suggestions, bug reports
> and ideas are very welcome. Please
> [open an issue](https://github.com/aimaruza/waon/issues).

waon is a portable and offline music player for your local files.
It builds a library by scanning folders you specify and reading their tags.

## Features

- **Libraries.** Support for multiple libraries. You can browse using the
  Artists, Albums, Playlists and Songs views.
- **Home page.** View your favorites, recently added songs, and a recap
  of what you've listened to most.
- **Queues.** Multiple play queues that can be resumed later.
- **Playlists.** Create and edit playlists, or import `.m3u` / `.m3u8`
  files.
- **Back up your data.** Export play history, playlists and
  favorites to a `.zip` file, so you can import it into another library.
  Tracks are matched by their tags, not file paths, so a backup survives moving or
  renaming your music.
- **Desktop integration.** Optional track notifications, plus
  system-wide media keys (Play/Pause, Next, Previous, Stop) on Windows.

Supported formats: MP3, FLAC, M4A, AAC, OGG, Opus, WAV and WMA.

## Platforms

waon is written in Python using Qt for the GUI. It has only been developed and tested on
**Windows 10/11 (64-bit)**. Linux and macOS aren't supported yet. If you
try it there, please [report](https://github.com/aimaruza/waon/issues)
what happens.

Some features rely on Windows APIs and are Windows-only: the global
media keys, battery-aware audio release, and native resizing and
snapping of the custom window frame.

## Getting started

Currently, there are no prebuilt downloads. waon runs from source.

You'll need **Python 3.9 (64-bit)**. The dependencies in
`requirements.txt` are pinned to the versions waon is tested with.

```powershell
git clone https://github.com/aimaruza/waon.git
cd waon
py -3.9 -m venv .env
.env\Scripts\python.exe -m pip install -r requirements.txt
.env\Scripts\python.exe main.py
```

On first launch a welcome screen walks you through creating your first
library.

### Tagging recommendations

To get the most out of waon, here are some recommended ways to tag your
files:

- Separate multiple artists with `/` in the Artist tag (e.g. `Artist A/Artist B`).
- Fill in the Album Artist tag. It is used to group an album's tracks together,
  even when individual tracks credit different artists.
- The Year/Date tag accepts a full date (`2023-11-01`) as well
  as a plain year. A full date sorts albums more precisely.

### Where your data lives

waon is **portable**. It keeps all of its data (library databases, artwork
cache, settings and logs) in a `data` folder inside the waon folder. It
only ever reads your music files and never modifies them. To move waon to
another PC, copy the whole folder.

The folder must be writable. If it isn't, waon tells you at startup. To
keep a test copy's data apart from your real library, set `WAON_DATA_DIR`
to another folder before launching.

### Building a standalone app (optional, Windows)

You can compile waon into a self-contained folder with
[Nuitka](https://nuitka.net/), which `requirements-dev.txt` installs:

```powershell
.env\Scripts\python.exe -m pip install -r requirements-dev.txt
.env\Scripts\python.exe -m nuitka main.py `
  --standalone --lto=no --enable-plugin=pyside6 `
  --windows-console-mode=disable `
  --windows-icon-from-ico=packaging/app_icon.ico `
  --output-filename=waon.exe --output-dir=build-nuitka `
  --include-package=ffpyplayer --nofollow-import-to=ffpyplayer.tests `
  "--include-data-files=.env\share\ffpyplayer\ffmpeg\bin\*.dll=share/ffpyplayer/ffmpeg/bin/" `
  "--include-data-files=.env\share\ffpyplayer\sdl\bin\*.dll=share/ffpyplayer/sdl/bin/" `
  "--include-data-files=waon\assets\phosphor-icons\*=waon/assets/phosphor-icons/" `
  "--include-data-files=waon\assets\logo\*=waon/assets/logo/" `
  --include-data-files=LICENSE=LICENSE `
  --include-data-files=CHANGELOG.md=CHANGELOG.md `
  --include-data-dir=packaging/third-party=third-party-licenses
```

The app ends up in `build-nuitka\main.dist\`. Run `waon.exe` from there.
It's unsigned, so Windows SmartScreen may warn you the first time you
run it.

## Contributing

waon is in beta, so your feedback shapes where it goes next. Bug reports,
feature suggestions and general impressions are all welcome in
[Issues](https://github.com/aimaruza/waon/issues). When submitting an issue,
please include all the necessary information and attach the latest log from
`data\logs` if possible.

## Built with

- [Qt for Python (PySide6)](https://doc.qt.io/qtforpython/) for the UI
- [ffpyplayer](https://github.com/matham/ffpyplayer) (FFmpeg + SDL) for
  audio playback
- [mutagen](https://github.com/quodlibet/mutagen) for reading tags
- [Phosphor Icons](https://phosphoricons.com/)
- SQLite for the library databases

## Credits

Logo by **Amer Safi** ([email](mailto:amerosafi@gmail.com) •
[Telegram](https://t.me/aosafi)).

## License

waon is licensed under the [GNU General Public License v3.0](LICENSE).

It bundles third-party components under their own licenses, including
FFmpeg (GPL-3.0), Qt (LGPL-3.0), ffpyplayer (LGPL-3.0), SDL (zlib), mutagen
(GPL-2.0-or-later) and Phosphor Icons (MIT). The full texts and source
links are in [`packaging/third-party/`](packaging/third-party/NOTICES.txt),
and a compiled build includes them in its `third-party-licenses` folder.
