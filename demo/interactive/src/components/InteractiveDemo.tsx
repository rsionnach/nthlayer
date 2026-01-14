import { useState, useCallback } from 'react';
import Editor from '@monaco-editor/react';
import { Terminal } from './Terminal';
import { executeCommand } from '../commands';

const DEFAULT_YAML = `# NthLayer Service Configuration
# Edit this YAML and run commands in the terminal

service:
  name: payment-api
  tier: critical
  owner: payments-team

slos:
  - name: availability
    target: 0.999
    window: 30d

  - name: latency_p99
    target: 200ms
    window: 7d

dependencies:
  - name: user-service
    critical: true
  - name: postgresql
    critical: true
  - name: stripe-api
    critical: true
`;

const SUGGESTIONS = [
  'nthlayer drift',
  'nthlayer validate-slo',
  'nthlayer deps',
  'nthlayer portfolio',
];

export function InteractiveDemo() {
  const [yamlContent, setYamlContent] = useState(DEFAULT_YAML);
  const [activeTab, setActiveTab] = useState<'editor' | 'terminal'>('editor');

  const handleCommand = useCallback(
    (command: string) => {
      return executeCommand(command, yamlContent);
    },
    [yamlContent]
  );

  const handleReset = () => {
    setYamlContent(DEFAULT_YAML);
  };

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-6xl h-[700px] flex flex-col rounded-xl overflow-hidden shadow-2xl border border-gray-800">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 bg-gray-900 border-b border-gray-800">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-lg">N</span>
            </div>
            <span className="text-white font-semibold text-lg">NthLayer</span>
          </div>
          <span className="text-gray-400 text-base hidden sm:inline">Interactive Demo</span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleReset}
            className="px-4 py-2 text-base text-gray-300 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
          >
            Reset
          </button>
          <a
            href="https://github.com/rsionnach/nthlayer"
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-2 text-base text-gray-300 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors hidden sm:inline-block"
          >
            GitHub
          </a>
        </div>
      </header>

      {/* Mobile tabs */}
      <div className="flex md:hidden border-b border-gray-800">
        <button
          onClick={() => setActiveTab('editor')}
          className={`flex-1 px-4 py-3 text-base font-medium transition-colors ${
            activeTab === 'editor'
              ? 'text-white bg-gray-800 border-b-2 border-blue-500'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          Editor
        </button>
        <button
          onClick={() => setActiveTab('terminal')}
          className={`flex-1 px-4 py-3 text-base font-medium transition-colors ${
            activeTab === 'terminal'
              ? 'text-white bg-gray-800 border-b-2 border-blue-500'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          Terminal
        </button>
      </div>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden bg-gray-900">
        {/* Editor panel - Desktop: always visible, Mobile: tab-controlled */}
        <div
          className={`w-full md:w-1/2 flex flex-col border-r border-gray-700 ${
            activeTab === 'editor' ? 'block' : 'hidden md:flex'
          }`}
        >
          <div className="px-4 py-3 bg-gray-800 border-b border-gray-700">
            <span className="text-gray-300 text-base font-medium">service.yaml</span>
          </div>
          <div className="flex-1">
            <Editor
              height="100%"
              defaultLanguage="yaml"
              value={yamlContent}
              onChange={(value) => setYamlContent(value || '')}
              theme="vs-dark"
              options={{
                minimap: { enabled: false },
                fontSize: 16,
                lineNumbers: 'on',
                scrollBeyondLastLine: false,
                wordWrap: 'on',
                tabSize: 2,
                automaticLayout: true,
                padding: { top: 16 },
                lineHeight: 24,
              }}
            />
          </div>
        </div>

        {/* Terminal panel - Desktop: always visible, Mobile: tab-controlled */}
        <div
          className={`w-full md:w-1/2 p-4 ${
            activeTab === 'terminal' ? 'block' : 'hidden md:flex'
          }`}
        >
          <Terminal onCommand={handleCommand} suggestions={SUGGESTIONS} />
        </div>
      </div>

      {/* Footer */}
      <footer className="px-4 py-3 bg-gray-900 border-t border-gray-800">
        <p className="text-gray-400 text-sm text-center">
          Reliability at build time, not incident time.{' '}
          <a
            href="https://nthlayer.dev"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:text-blue-300"
          >
            Learn more
          </a>
        </p>
      </footer>
      </div>
    </div>
  );
}
