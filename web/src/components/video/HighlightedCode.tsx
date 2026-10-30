import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import javascript from 'react-syntax-highlighter/dist/esm/languages/prism/javascript'
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python'
import bash from 'react-syntax-highlighter/dist/esm/languages/prism/bash'
import json from 'react-syntax-highlighter/dist/esm/languages/prism/json'
import { useAppearance } from '../../lib/theme'
import './summary-code.css'

for (const [name, language] of Object.entries({ javascript, python, bash, json })) {
  SyntaxHighlighter.registerLanguage(name, language)
}

export default function HighlightedCode({ language, children }: { language: string; children: string }) {
  const { design, theme } = useAppearance()
  const themed = design === 'editorial' || theme === 'light'
  return <SyntaxHighlighter className="summary-code" style={themed ? {} : vscDarkPlus} useInlineStyles={!themed} language={language} PreTag="div"
    customStyle={{ margin: 0, borderRadius: '0.5rem', fontSize: '0.8125rem' }}>{children}</SyntaxHighlighter>
}
