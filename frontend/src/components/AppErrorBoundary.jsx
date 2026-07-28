import { Component } from "react";

export class AppErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("[sentriface-ui] unrecoverable render error", error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main style={{ maxWidth: 720, margin: "10vh auto", padding: 24, fontFamily: "system-ui" }}>
        <h1>SentriFace could not display this screen</h1>
        <p>Your database and photos were not changed. Reload the app to recover the interface.</p>
        <pre style={{ whiteSpace: "pre-wrap", color: "#b42318" }}>
          {String(this.state.error?.message || this.state.error)}
        </pre>
        <button type="button" onClick={() => window.location.reload()}>Reload SentriFace</button>
      </main>
    );
  }
}
