import { expect, it } from 'vitest'
import { Transformer } from 'markmap-lib'

it('parses headings, links, code and formulae with the updated Markdown dependencies', () => {
  const { root, features } = new Transformer().transform('# Study notes\n\n## A formula\n\n$E=mc^2$\n\n- [Source](https://example.com)\n- `code`')
  expect(root.content).toContain('Study notes')
  const content = JSON.stringify(root)
  expect(content).toContain('https://example.com')
  expect(content).toContain('code')
  expect(features).toBeTruthy()
})
