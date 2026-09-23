# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('ca_bundle_netfree.pem', '.')],
    hiddenimports=[
        'chess', 'chess.pgn', 'sound_effects', 'theme_style',
        'chess_engine', 'chess_board_widget', 'chess_window',
        'checkers_engine', 'checkers_board_widget', 'checkers_window',
        'backgammon_engine', 'backgammon_board_widget', 'backgammon_window',
        'platform_window', 'chess_sync', 'google_sheets_client',
        'googleapiclient', 'google_auth_oauthlib', 'google.auth.transport.requests'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NetFreeChess',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
