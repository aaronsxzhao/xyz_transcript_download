import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import javascript from 'react-syntax-highlighter/dist/esm/languages/prism/javascript'
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python'
import bash from 'react-syntax-highlighter/dist/esm/languages/prism/bash'
import json from 'react-syntax-highlighter/dist/esm/languages/prism/json'

for (const [name, language] of Object.entries({ javascript, python, bash, json })) {
  SyntaxHighlighter.registerLanguage(name, language)
}

export default function HighlightedCode({ language, children }: { language: string; children: string }) {
  return <SyntaxHighlighter style={vscDarkPlus} language={language} PreTag="div"
    customStyle={{ margin: 0, borderRadius: '0.5rem', fontSize: '0.8125rem' }}>{children}</SyntaxHighlighter>
}
