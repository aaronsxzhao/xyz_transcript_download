import { Component, type ReactNode } from 'react'
import { reloadFreshPage } from '../lib/chunkRecovery'

export default class PageErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() { return { failed: true } }

  render() {
    if (!this.state.failed) return this.props.children
    return <div role="alert" className="min-h-screen bg-dark-bg text-gray-200 flex flex-col items-center justify-center gap-4 p-6">
      <h1 className="text-xl font-semibold">This page could not open</h1>
      <p>Reload to get the latest version and try again.</p>
      <button className="px-4 py-2 bg-indigo-600 rounded-lg" onClick={reloadFreshPage}>Reload page</button>
      <a className="underline" href="/">Back to dashboard</a>
    </div>
  }
}
