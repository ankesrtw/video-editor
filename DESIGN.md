---
version: alpha
name: "Video Editor"
description: "A compact, dark desktop workspace for reliable FFmpeg video edits."
colors:
  background: "#1e1e2e"
  surface: "#313244"
  surface-raised: "#45475a"
  text: "#cdd6f4"
  muted: "#a6adc8"
  primary: "#89b4fa"
  success: "#a6e3a1"
  warning: "#f9e2af"
  danger: "#f38ba8"
typography:
  ui:
    fontFamily: "Helvetica, Arial, sans-serif"
  mono:
    fontFamily: "Courier, monospace"
rounded:
  DEFAULT: "0.25rem"
spacing:
  control-gap: "0.375rem"
  section-gap: "0.5rem"
components:
  button: {}
  input: {}
  panel: {}
  status-log: {}
---

# Video Editor Design System

## Overview

### Creative North Star

An edit-bay control panel: compact, low-glare, and calm enough to keep source, settings, and FFmpeg feedback readable during long renders.

### Product context and register

- **Audience and primary job:** People making practical video edits who need direct, understandable controls for FFmpeg operations.
- **Target market(s) and evidence:** General desktop users; the repository exposes an English Tkinter interface and no market-specific requirements.
- **Locale(s) and language policy:** English labels and plain action language; system fonts supply OS/script fallback.
- **Usage scene:** Desktop, keyboard/mouse, with several edit tools open in sequence.
- **Register:** Product utility.
- **Memorable signature:** The live command and status console makes every edit inspectable.
- **Restraint:** Media settings and export actions remain conventional and densely readable.
- **Anti-references:** Timeline-heavy consumer NLE metaphors and decorative streaming-app cards would obscure direct tool workflows.
- **Token ownership/runtime mapping:** `video_editor.py` is the runtime source of truth; this file records its ttk/Tk colors and typography.

## Colors

`background` and `surface` form the low-contrast workspace. `primary` marks primary actions and titles. `success`, `warning`, and `danger` are reserved for render status and errors; messages always include text as well as color.

## Typography

The UI uses the system Helvetica/Arial stack for editing controls and Courier for executable commands and live FFmpeg output. Bold is reserved for task headings and section labels.

## Layout

Tools are separate scrollable notebook tabs so the active workflow owns vertical scrolling. Each tool keeps file selection above settings and puts the irreversible render action last. The status console has a stable lower pane to avoid moving primary controls during a render.

## Elevation & Depth

Hierarchy comes from tonal panels, group borders, and notebook separation rather than strong shadows. The log is the darkest surface to separate generated output from editable settings.

## Shapes

Controls use a restrained 4px corner radius. Inputs and buttons share the same compact geometry; grouped settings use thin borders rather than card stacks.

## Components

### Foundational visual states

Native ttk controls provide focus and keyboard behavior. A running render changes the window cursor, progress state, and status text while keeping controls in place. Errors remain visible in the console and are also communicated by text dialogs.

### Buttons and actions

Accent buttons run a render; neutral buttons select media or alter an edit list. Primary actions use explicit verbs such as “Add Image to Video.”

### Navigation and data display

Notebook tabs group independent operations. Treeviews show ordered content when order changes output.

### Forms and overlays

File picker buttons provide the standard non-drag media-selection path. Input validation happens before a render begins and explains how to recover.

### Iconography

Text labels remain mandatory; the play symbol only reinforces render actions.

### Motion

UI motion is limited to progress feedback. Rendered image fades and zooms are content choices, not UI decoration.

### Content and data visualization

Copy is concise and action-led. Time fields use seconds and explicitly explain timeline reference points.

## Do's and Don'ts

- **Do:** Keep source selection, timing, and render controls in their execution order.
- **Do:** Preserve the console as the authoritative record of the generated FFmpeg command.
- **Don't:** Hide required settings behind decoration or hover-only controls.
- **Don't:** Use color as the only indication of render success or failure.
