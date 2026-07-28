import { Component } from 'react'

/**
 * Catches texture load errors (404, CORS, decode failure) thrown by
 * drei useTexture and renders `fallback` instead of hanging Suspense
 * or crashing the canvas. Retries when `resetKey` (the URL) changes.
 */
export default class TextureErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidUpdate(prevProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.failed) {
      this.setState({ failed: false })
    }
  }

  render() {
    if (this.state.failed) return this.props.fallback ?? null
    return this.props.children
  }
}
