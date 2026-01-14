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
    <div className="h-full flex flex-col bg-gray-950">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 bg-gray-900 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-sm">N</span>
            </div>
            <span className="text-white font-semibold">NthLayer</span>
          </div>
          <span className="text-gray-500 text-sm hidden sm:inline">Interactive Demo</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleReset}
            className="px-3 py-1.5 text-sm text-gray-300 hover:text-white bg-gray-800 hover:bg-gray-700 rounded transition-colors"
          >
            Reset
          </button>
          <a
            href="https://github.com/rob-fox-consulting/trellis"
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 text-sm text-gray-300 hover:text-white bg-gray-800 hover:bg-gray-700 rounded transition-colors hidden sm:inline-block"
          >
            GitHub
          </a>
        </div>
      </header>

      {/* Mobile tabs */}
      <div className="flex md:hidden border-b border-gray-800">
        <button
          onClick={() => setActiveTab('editor')}
          className={`flex-1 px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === 'editor'
              ? 'text-white bg-gray-800 border-b-2 border-blue-500'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          Editor
        </button>
        <button
          onClick={() => setActiveTab('terminal')}
          className={`flex-1 px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === 'terminal'
              ? 'text-white bg-gray-800 border-b-2 border-blue-500'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          Terminal
        </button>
      </div>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Editor panel - Desktop: always visible, Mobile: tab-controlled */}
        <div
          className={`w-full md:w-1/2 flex flex-col border-r border-gray-800 ${
            activeTab === 'editor' ? 'block' : 'hidden md:flex'
          }`}
        >
          <div className="px-4 py-2 bg-gray-900 border-b border-gray-800">
            <span className="text-gray-400 text-sm font-medium">service.yaml</span>
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
                fontSize: 14,
                lineNumbers: 'on',
                scrollBeyondLastLine: false,
                wordWrap: 'on',
                tabSize: 2,
                automaticLayout: true,
                padding: { top: 16 },
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
      <footer className="px-4 py-2 bg-gray-900 border-t border-gray-800">
        <p className="text-gray-500 text-xs text-center">
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
  );
}
