
BRAND = "#417BFF"
BRAND_HOVER = "#2F66E8"
BRAND_SOFT = "#EAF1FF"
BRAND_SOFT_HOVER = "#DCE7FF"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F5F5F7"
TEXT = "#1A1A1A"
TEXT_MUTED = "#6B6B70"
BORDER = "#E3E3E8"
MENU_BORDER = "#C4C3CC"
ICON = "#56555F"
DANGER = "#B42318"
CLOSE_HOVER = "#E81123"

DISABLED = "#94939C"
TOGGLE_OFF = "#C9C8D0"
SCRIM = "rgba(26, 26, 26, 0.45)"
RAIL_BG = "#FAFAFC"

LIBRARY_COLORS = (
    BRAND, "#E6540B", "#369950", "#198AA6", "#BF0A16", "#BF0A6A",
    "#7543BF", "#626673",
)


def build_stylesheet():
    return """
    QWidget {{
        background: {surface};
        color: {text};
        font-family: 'Segoe UI', sans-serif;
        font-size: 14px;
    }}
    QMainWindow, #CentralArea {{ background: {surface}; }}

    QListView {{
        background: {surface};
        border: none;
        outline: none;
        /* No bottom padding: the detail pane's bottom edge sits flush
           against the transport bar (no margin between browse_page and
           transport), and a bottom inset here read as a gap above the
           seek bar. */
        padding: 4px 4px 0px 4px;
    }}
    QListView::item {{
        padding: 10px 12px;
        border-radius: 8px;
        margin: 1px 6px;
    }}
    QListView::item:hover {{ background: {surface_alt}; }}
    QListView::item:selected {{
        background: {brand_soft};
        color: {text};
    }}
    /* RootList (library_dialog.py) hosts a custom RootRow widget per item,
       which already manages its own padding -- the padding/margin above is
       tuned for the browse panes' plain rows and, applied here too, ate
       space out from under RootRow's own two-line layout. */
    QListWidget#RootList::item {{
        padding: 0px;
        margin: 0px;
        border-radius: 0px;
    }}
    QListWidget#RootList::item:hover {{ background: transparent; }}

    /* Unified scroll handles: no arrow buttons, invisible against the pane
       until it's hovered, accent-coloured handle when it appears. Hover is
       driven by a `hovering` dynamic property set directly on the scrollbar
       (see browse_panes._HoverScrollView) rather than a QSS :hover
       ancestor selector, which does not reliably repaint the handle. */
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 0px;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 6px;
        margin: 0px;
    }}
    QScrollBar::handle {{
        background: transparent;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical {{ min-height: 24px; }}
    QScrollBar::handle:horizontal {{ min-width: 24px; }}
    QScrollBar[hovering="true"]::handle {{ background: {brand}; }}
    QScrollBar::handle:pressed {{ background: {brand_hover}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        width: 0px;
        height: 0px;
        background: none;
        border: none;
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

    /* PopupMenu -- the shared popup replacing QMenu everywhere (see
       waon/ui/popup_menu.py's module docstring). Rows hover via the
       [hovering] property pattern so the fill reaches every edge of
       the row. Square, unshadowed card; MENU_BORDER (not BORDER) is
       what keeps it from blending into the white page under it. */
    #PopupMenu {{
        background: {surface};
        border: 1px solid {menu_border};
    }}
    #PopupMenuRow {{ background: transparent; }}
    #PopupMenuRow[hovering="true"] {{ background: {surface_alt}; }}
    #PopupMenuDividerHolder {{ background: transparent; }}
    #PopupMenuDivider {{ background: {border}; }}

    #TransportBar {{
        background: {surface};
        border-top: 1px solid {border};
    }}
    #NowTitle {{ font-weight: 600; font-size: 14px; color: {text}; }}
    #NowTitle[idle="true"] {{ font-weight: 400; color: {muted}; }}
    #NowArtist {{ font-size: 12px; color: {muted}; }}
    #TrackNotification {{ background: transparent; }}
    #NotifCard {{
        background: {surface};
        border: 1px solid {border};
        border-radius: 10px;
    }}
    #NotifCard QLabel {{ background: transparent; }}
    #NotifTitle {{ font-weight: 600; font-size: 14px; color: {text}; }}
    #NotifArtist {{ font-size: 12px; color: {muted}; }}
    #TimeLabel {{ color: {muted}; font-size: 12px; }}
    #TimeElapsed {{ color: {text}; font-size: 12px; font-weight: 600; }}

    QPushButton#AddButton {{
        background: {brand};
        color: white;
        border: none;
        border-radius: 8px;
        padding: 8px 16px;
        font-weight: 600;
    }}
    QPushButton#AddButton:hover {{ background: {brand_hover}; }}

    QToolButton {{
        background: transparent;
        border: none;
        border-radius: 18px;
        padding: 6px;
        font-size: 18px;
    }}
    QToolButton:hover {{ background: {surface}; }}
    QToolButton#PlayButton {{
        background: {brand};
        color: white;
        min-width: 40px;
        min-height: 40px;
    }}
    QToolButton#PlayButton:hover {{ background: {brand_hover}; }}

    QSlider::groove:horizontal {{
        height: 4px;
        background: {border};
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {brand};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {brand};
        width: 12px;
        margin: -5px 0;
        border-radius: 6px;
    }}
    QSlider#SeekSlider, QSlider#VolumeSlider {{
        background: transparent; border: none;
    }}
    QSlider#SeekSlider::groove:horizontal, QSlider#VolumeSlider::groove:horizontal {{
        height: 4px; background: {border}; border: none; border-radius: 2px;
    }}
    /* SeekSlider alone is pinned flush to the bar's own top edge (a
       full-width overlay strip, not an inline control -- see _CONTENT_TOP
       in transport_bar.py) by its own 12px box; VolumeSlider sits inline
       among the speaker icon/time labels instead and must stay vertically
       centered in its own, same-height box like any other row control.
       Both shared this rule (and `top`) through 84fed8e, which was only
       ever fixing the seek groove -- that silently pulled the volume
       groove off-center from the speaker icon beside it. */
    QSlider#SeekSlider::groove:horizontal {{
        subcontrol-position: top; subcontrol-origin: margin;
    }}
    QSlider#SeekSlider::add-page:horizontal, QSlider#VolumeSlider::add-page:horizontal {{
        background: {border}; border: none; border-radius: 2px;
    }}
    QSlider#SeekSlider::sub-page:horizontal, QSlider#VolumeSlider::sub-page:horizontal {{
        background: {brand}; border: none; border-radius: 2px;
    }}
    QSlider#SeekSlider::handle:horizontal, QSlider#VolumeSlider::handle:horizontal {{
        background: transparent; border: none;
        width: 0px; height: 0px; margin: 0px;
    }}

    #TitleBar {{
        background: {surface_alt};
        border-bottom: 1px solid {border};
    }}
    /* Otherwise the blanket `QWidget` background rule above paints these
       plain, unnamed QWidget containers opaque white, hiding the bar's own
       tint underneath them. */
    #TitleBarZone {{ background: transparent; }}
    /* Same rule for the logo label: the mark's loops and margins are
       see-through and must show the bar, not a white box. */
    #TitleBarLogo {{ background: transparent; }}
    #LibraryBar {{ background: transparent; }}
    #LibrarySplitButton {{
        border: 1px solid {border};
        background: {surface};
    }}
    #LibrarySplitDivider {{ background: {border}; }}
    #TrackCount {{ color: {muted}; font-size: 12px; }}

    #NavRail {{
        background: {rail_bg};
        border-right: 1px solid {border};
    }}

    #ListPaneHeader {{
        color: {text};
        font-size: 14px;
        font-weight: 600;
        padding: 16px 14px 10px 14px;
    }}
    #DetailPaneHeader {{
        color: {text};
        font-size: 14px;
        font-weight: 600;
        padding: 16px 14px 10px 14px;
    }}
    #ListHeaderDivider, #DetailHeaderDivider, #DetailPaneDivider {{
        background: {border};
    }}
    QSplitter::handle:horizontal {{
        background: {border};
    }}
    #ListPane, #DetailPane, #GridPane {{ background: {surface}; border: none; }}
    #PaneEmpty {{ color: {muted}; font-size: 13px; }}

    #ScanScrim {{ background: {scrim}; }}
    #ScanCard {{
        background: {surface};
        border: 1px solid {border};
        border-radius: 12px;
    }}
    #ScanCard QLabel {{ background: transparent; }}
    #ScanTitle {{ font-weight: 600; font-size: 15px; color: {text}; }}
    #ScanDetail {{ font-size: 12px; color: {muted}; }}
    QProgressBar#ScanBar {{
        background: {surface_alt};
        border: none;
        border-radius: 3px;
        min-height: 6px;
        max-height: 6px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar#ScanBar::chunk {{ background: {brand}; border-radius: 3px; }}

    #HomePage {{ background: {surface}; }}
    /* The Currently playing page (now_playing_page.py). */
    #NowPlayingPage, #NowPlayingQueue {{ background: {surface}; border: none; }}
    #NowPlayingTitle {{ font-size: 22px; font-weight: 600; color: {text}; }}
    #NowPlayingLink {{ font-size: 14px; color: {muted}; }}
    #NowPlayingLink:hover {{ color: {brand}; }}
    #NowPlayingQueueTitle {{ font-size: 16px; font-weight: 600; color: {text}; }}
    #NowPlayingQueueOwner {{ font-size: 12px; color: {muted}; }}
    /* QScrollArea and its internal viewport widget both paint their own
       opaque background by default, which would otherwise show as a
       mismatched rectangle behind the columns -- both must be made
       transparent for the page's own background to show through. */
    #HomeScrollArea, #HomeScrollArea > QWidget > QWidget {{
        background: transparent;
        border: none;
    }}
    QPushButton#HomePeriodTab {{
        background: {surface_alt};
        color: {muted};
        border: none;
        border-radius: 0px;
        padding: 6px 14px;
        font-weight: 600;
        font-size: 12px;
    }}
    QPushButton#HomePeriodTab:checked {{
        background: {brand};
        color: white;
    }}
    QPushButton#HomePeriodNavArrow {{
        background: transparent;
        color: {text};
        border: none;
        font-size: 14px;
        font-weight: 700;
        padding: 4px 8px;
    }}
    QPushButton#HomePeriodNavArrow:disabled {{
        color: {muted};
    }}
    #HomeStatTile {{
        background: {surface_alt};
        color: {text};
        font-size: 20px;
        font-weight: 700;
        padding: 12px 18px;
        margin: 10px 0px 18px 0px;
        min-height: 28px;
    }}
    #HomeSectionTitle {{
        color: {muted};
        font-size: 11px;
        font-weight: 600;
    }}
    #HomeSectionEmpty {{ color: {muted}; font-size: 13px; padding: 8px 0px; }}
    QListView#HomeSectionList {{ background: {surface}; border: none; outline: none; }}

    #RootPath {{ font-size: 13px; color: {text}; }}
    #RootCount {{ font-size: 12px; color: {muted}; }}
    #DialogHint {{ font-size: 12px; color: {muted}; }}

    /* Track info card (waon/ui/track_info_dialog.py). */
    #TrackInfoTitle {{ font-weight: 600; font-size: 17px; color: {text}; }}
    #TrackInfoKey {{ font-size: 13px; color: {muted}; }}
    #TrackInfoValue {{ font-size: 13px; color: {text}; }}
    #TrackInfoDivider {{ background: {border}; }}
    QPushButton#TrackInfoReset {{
        background: transparent;
        color: {danger};
        border: 1px solid {border};
        padding: 5px 10px;
        font-size: 13px;
    }}
    QPushButton#TrackInfoReset:hover {{ background: {surface_alt}; }}
    QPushButton#TrackInfoReset:disabled {{ color: {disabled}; }}
    #DialogError {{ font-size: 12px; color: {danger}; }}
    #SettingsInfoCard, #SettingsGroupCard, #SettingsDangerCard {{
        background: {surface};
        border: 1px solid {border};
    }}
    #SettingsRowDivider {{ background: {border}; }}
    #SettingsRow {{ background: transparent; }}
    #SettingsRow[hovering="true"] {{ background: {surface_alt}; }}
    #SettingsRowCount {{ background: transparent; color: {muted}; font-size: 12px; }}
    #Toast {{
        background: {brand};
        border-radius: 0px;
    }}
    #ToastLabel {{
        background: transparent;
        color: white;
        font-size: 13px;
        font-weight: 600;
    }}
    #SettingsScrim {{ background: {scrim}; }}
    #SettingsCard {{
        background: {surface};
        border: 1px solid {border};
        border-radius: 0px;
    }}
    #SettingsCard QLabel {{ background: transparent; }}
    #SettingsHeaderTitle {{ font-weight: 600; font-size: 15px; color: {text}; }}
    #DialogScrim {{ background: {scrim}; }}
    #DialogCard {{
        background: {surface};
        border: 1px solid {border};
        border-radius: 0px;
    }}
    #DialogCard QLabel {{ background: transparent; }}
    #DialogHeaderTitle {{ font-weight: 600; font-size: 15px; color: {text}; }}
    #SettingsSidebarPanel {{
        background: {rail_bg};
        border-right: 1px solid {border};
    }}
    QListWidget#SettingsSidebar, QListWidget#SettingsPinnedSidebar {{
        background: transparent;
        border: none;
        outline: none;
    }}
    QListWidget#SettingsSidebar {{ padding: 6px 0px; }}
    QListWidget#SettingsPinnedSidebar {{ padding: 0px; }}
    QListWidget#SettingsSidebar::item, QListWidget#SettingsPinnedSidebar::item {{
        padding: 8px 14px;
        border-radius: 0px;
        margin: 0px;
    }}
    QListWidget#SettingsSidebar::item:hover,
    QListWidget#SettingsPinnedSidebar::item:hover {{ background: {surface_alt}; }}
    QListWidget#SettingsSidebar::item:selected,
    QListWidget#SettingsPinnedSidebar::item:selected {{
        background: {brand_soft};
        color: {text};
    }}
    #SettingsPlaceholder {{ color: {muted}; font-size: 13px; }}
    #SettingsHeaderRule, #SettingsSidebarRule {{ background: {border}; }}
    QScrollArea#SettingsPageScroll {{ background: {surface}; border: none; }}
    #SettingsPage {{ background: {surface}; }}
    #SettingsPageTitle {{ font-size: 15px; font-weight: 600; color: {text}; }}
    #SettingsGroupLabel {{ font-size: 11px; font-weight: 600; color: {muted}; }}
    #SettingsRow QLabel {{ background: transparent; }}
    #SettingsRowLabel {{ font-size: 13px; color: {text}; }}
    #SettingsRowHint {{ font-size: 11px; color: {muted}; }}
    #SettingsRow QLabel:disabled {{ color: {disabled}; }}
    QPushButton#SettingsChoiceButton, QPushButton#AboutOpenFolder {{
        background: {surface_alt};
        border: 1px solid {border};
        border-radius: 0px;
        padding: 4px 10px;
        color: {text};
        font-size: 13px;
    }}
    QPushButton#SettingsChoiceButton:hover, QPushButton#AboutOpenFolder:hover {{
        border: 1px solid {brand};
    }}
    QPushButton#SettingsChoiceButton:disabled {{ color: {disabled}; }}
    #AboutName {{ font-size: 18px; font-weight: 600; color: {text}; }}
    #AboutMeta {{ font-size: 12px; color: {muted}; }}
    #AboutPath {{ font-size: 12px; color: {muted}; }}
    QTextBrowser#ChangelogText {{
        background: transparent;
        border: none;
        color: {text};
    }}
    QPushButton#AboutLink {{
        background: transparent;
        border: none;
        color: {brand};
        text-align: left;
        padding: 0px;
    }}
    QPushButton#AboutLink:hover {{ text-decoration: underline; }}
    QLineEdit {{
        background: {surface_alt};
        border: 1px solid {border};
        border-radius: 8px;
        padding: 7px 10px;
    }}
    QLineEdit:focus {{ border: 1px solid {brand}; }}
    QLineEdit:disabled {{ background: {border}; color: {muted}; }}
    QDialogButtonBox QPushButton {{
        background: {surface_alt};
        border: 1px solid {border};
        border-radius: 8px;
        padding: 7px 16px;
    }}
    QDialogButtonBox QPushButton:default {{
        background: {brand};
        color: white;
        border: none;
        font-weight: 600;
    }}
    QDialogButtonBox QPushButton:default:disabled {{ background: {border}; }}

    #WelcomeBrandPanel {{ background: {brand}; }}
    /* Child QLabels need an explicit transparent background too, or the
       blanket QWidget rule at the top of this sheet paints them opaque and
       hides the brand panel underneath -- see #NotifCard QLabel above for
       the same fix applied to a different card. */
    #WelcomeBrandPanel QLabel {{ background: transparent; }}
    #WelcomeWordmark {{
        color: white;
        font-size: 20px;
        font-weight: 700;
        letter-spacing: 0.04em;
    }}
    #WelcomeHeadline {{
        color: {text};
        font-size: 22px;
        font-weight: 700;
    }}
    #WelcomeSubtext {{ color: {muted}; font-size: 13px; }}
    QPushButton#WelcomeCreateButton, QPushButton#WizardPrimary {{
        background: {brand};
        color: white;
        border: none;
        border-radius: 0px;
        padding: 10px 18px;
        font-weight: 600;
    }}
    QPushButton#WelcomeCreateButton:hover, QPushButton#WizardPrimary:hover {{
        background: {brand_hover};
    }}
    QPushButton#WizardPrimary:disabled {{ background: {border}; }}
    QPushButton#WizardNextButton {{
        background: {brand};
        border: none;
        border-radius: 26px;
    }}
    QPushButton#WizardNextButton:hover {{ background: {brand_hover}; }}
    QPushButton#WizardNextButton:disabled {{ background: {border}; }}
    QPushButton#WizardBackButton {{
        background: {brand_soft};
        border: none;
        border-radius: 26px;
    }}
    QPushButton#WizardBackButton:hover {{ background: {brand_soft_hover}; }}
    QPushButton#WizardSecondary {{
        background: transparent;
        color: {text};
        border: 1px solid {border};
        border-radius: 0px;
        padding: 10px 18px;
    }}
    QPushButton#WizardSecondary:hover {{ border: 1px solid {brand}; color: {text}; }}
    QPushButton#WizardSecondary:disabled {{ color: {border}; }}
    #SetupWizard {{ background: {surface}; }}
    #WizardTitle {{ color: {text}; font-size: 24px; font-weight: 700; }}
    #WizardSubtext {{ color: {muted}; font-size: 14px; }}
    #WizardSectionTitle {{ color: {text}; font-weight: 600; }}
    #WizardDivider {{ background: {border}; }}
    /* Setup wizard folder cards: square, bordered, the add action as the
       card's own last row. Rows hover by background, per the app-wide
       convention. */
    #FolderCard {{ background: {surface}; border: 1px solid {border}; }}
    #FolderCardDivider {{ background: {border}; }}
    QListWidget#FolderCardList {{ background: transparent; border: none; }}
    QListWidget#FolderCardList::item {{
        padding: 0px;
        margin: 0px;
        border-radius: 0px;
    }}
    QListWidget#FolderCardList::item:hover {{ background: {surface_alt}; }}
    /* The row and everything in it stay see-through, so the item's hover
       tint covers the whole row instead of showing around a white path
       label and button (the blanket QWidget rule paints them opaque). */
    #FolderRow, #FolderRow * {{ background: transparent; }}
    /* Always visible here: the global rule keeps handles transparent
       until a browse pane's hover tracking turns them on, which left
       these lists with no visible scrollbar at all. */
    QListWidget#FolderCardList QScrollBar::handle {{ background: {toggle_off}; }}
    QListWidget#FolderCardList QScrollBar::handle:hover {{ background: {brand}; }}
    /* Same fix for the Add-to-playlist checklist (playlist_dialog.py). */
    QListWidget#PlaylistPickList QScrollBar::handle {{ background: {toggle_off}; }}
    QListWidget#PlaylistPickList QScrollBar::handle:hover {{ background: {brand}; }}
    /* ...and the Add-to-queue checklist (queue_dialog.py). */
    QListWidget#QueuePickList QScrollBar::handle {{ background: {toggle_off}; }}
    QListWidget#QueuePickList QScrollBar::handle:hover {{ background: {brand}; }}
    QPushButton#FolderCardAdd {{
        background: transparent;
        border: none;
        border-radius: 0px;
        text-align: left;
        padding: 12px 14px;
        color: {text};
        font-weight: 600;
    }}
    QPushButton#FolderCardAdd:hover {{ background: {surface_alt}; }}
    """.format(
        surface=SURFACE,
        surface_alt=SURFACE_ALT,
        toggle_off=TOGGLE_OFF,
        text=TEXT,
        muted=TEXT_MUTED,
        border=BORDER,
        menu_border=MENU_BORDER,
        brand=BRAND,
        brand_hover=BRAND_HOVER,
        brand_soft=BRAND_SOFT,
        brand_soft_hover=BRAND_SOFT_HOVER,
        rail_bg=RAIL_BG,
        scrim=SCRIM,
        danger=DANGER,
        disabled=DISABLED,
    )
