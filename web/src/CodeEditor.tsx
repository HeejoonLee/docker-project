import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands'
import { markdown } from '@codemirror/lang-markdown'
import { yamlFrontmatter } from '@codemirror/lang-yaml'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { highlightSelectionMatches, searchKeymap } from '@codemirror/search'
import { EditorState } from '@codemirror/state'
import {
  drawSelection, EditorView, highlightActiveLine, highlightActiveLineGutter, highlightSpecialChars, keymap, lineNumbers,
} from '@codemirror/view'
import { tags as t } from '@lezer/highlight'
import { useEffect, useRef } from 'react'

// Colors come from the app's CSS variables, so the editor follows the light and dark palettes.
const highlight = HighlightStyle.define([
  { tag: t.heading, color: 'var(--text)', fontWeight: '700' },
  { tag: [t.processingInstruction, t.meta, t.contentSeparator], color: 'var(--muted)' },
  { tag: t.strong, fontWeight: '700' },
  { tag: t.emphasis, fontStyle: 'italic' },
  { tag: t.strikethrough, textDecoration: 'line-through' },
  { tag: [t.link, t.url], color: 'var(--highlight)' },
  { tag: t.monospace, color: 'var(--ok)' },
  { tag: t.quote, color: 'var(--text-2)', fontStyle: 'italic' },
  { tag: [t.propertyName, t.definition(t.propertyName)], color: 'var(--highlight)' },
  { tag: [t.number, t.bool, t.null, t.atom], color: 'var(--warn)' },
  { tag: t.comment, color: 'var(--muted)', fontStyle: 'italic' },
])

const theme = EditorView.theme({
  '&': { height: '100%', fontSize: '0.84rem', color: 'var(--text)', backgroundColor: 'var(--surface)' },
  '&.cm-focused': { outline: 'none' },
  '.cm-scroller': { fontFamily: 'var(--mono)', lineHeight: '1.6' },
  '.cm-content': { padding: '12px 0', caretColor: 'var(--text)' },
  '.cm-line': { padding: '0 18px 0 12px' },
  '.cm-gutters': { backgroundColor: 'var(--surface-2)', color: 'var(--muted)', borderRight: '1px solid var(--border)' },
  '.cm-lineNumbers .cm-gutterElement': { padding: '0 10px 0 14px' },
  '.cm-activeLine': { backgroundColor: 'color-mix(in srgb, var(--surface-3) 45%, transparent)' },
  '.cm-activeLineGutter': { backgroundColor: 'var(--surface-3)', color: 'var(--text)' },
  '.cm-cursor': { borderLeftColor: 'var(--text)' },
  '&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground': {
    backgroundColor: 'color-mix(in srgb, var(--highlight) 22%, transparent)',
  },
  '.cm-selectionMatch': { backgroundColor: 'var(--highlight-soft)' },
  '.cm-panels': { backgroundColor: 'var(--surface-2)', color: 'var(--text)', borderColor: 'var(--border)' },
})

/** A CodeMirror editor for Article Markdown with YAML frontmatter. Read-only when `onChange` is omitted. */
export default function CodeEditor({ value, onChange }: { value: string; onChange?: (value: string) => void }) {
  const host = useRef<HTMLDivElement>(null)
  const view = useRef<EditorView | null>(null)
  const onChangeRef = useRef(onChange)
  const readOnly = !onChange

  useEffect(() => { onChangeRef.current = onChange }, [onChange])

  useEffect(() => {
    if (!host.current) return
    const v = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: value,
        extensions: [
          lineNumbers(),
          highlightActiveLineGutter(),
          highlightSpecialChars(),
          drawSelection(),
          readOnly ? [] : [history(), highlightActiveLine()],
          EditorView.lineWrapping,
          yamlFrontmatter({ content: markdown() }),
          syntaxHighlighting(highlight),
          highlightSelectionMatches(),
          keymap.of([...defaultKeymap, ...historyKeymap, ...searchKeymap, ...(readOnly ? [] : [indentWithTab])]),
          EditorState.readOnly.of(readOnly),
          EditorView.editable.of(!readOnly),
          EditorView.updateListener.of((u) => { if (u.docChanged) onChangeRef.current?.(u.state.doc.toString()) }),
          theme,
        ],
      }),
    })
    view.current = v
    if (!readOnly) v.focus()
    return () => { v.destroy(); view.current = null }
    // The document is only seeded here; later outside changes go through the effect below.
  }, [readOnly])

  // Replace the document when the value changes from outside, e.g. after a revision arrives.
  useEffect(() => {
    const v = view.current
    if (v && v.state.doc.toString() !== value) v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: value } })
  }, [value])

  return <div className="code-editor" ref={host} />
}
