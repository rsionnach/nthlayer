import { useState, useRef, useEffect, KeyboardEvent, useMemo } from 'react';

interface TerminalProps {
  onCommand: (command: string) => { output: string; isError?: boolean; delay?: number };
  suggestions?: string[];
}

interface HistoryEntry {
  command: string;
  output: string;
  isError?: boolean;
}

// Parse ANSI color codes to React elements
function parseAnsi(text: string): React.ReactNode[] {
  const ansiRegex = /\x1b\[(\d+)m/g;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let currentStyle: React.CSSProperties = {};
  let match;
  let keyIndex = 0;

  const colorMap: Record<number, React.CSSProperties> = {
    0: {}, // Reset
    31: { color: '#ef4444' }, // Red
    32: { color: '#22c55e' }, // Green
    33: { color: '#eab308' }, // Yellow
    34: { color: '#3b82f6' }, // Blue
    35: { color: '#a855f7' }, // Magenta
    36: { color: '#06b6d4' }, // Cyan
    37: { color: '#f3f4f6' }, // White
  };

  while ((match = ansiRegex.exec(text)) !== null) {
    // Add text before this match with current style
    if (match.index > lastIndex) {
      const segment = text.slice(lastIndex, match.index);
      if (Object.keys(currentStyle).length > 0) {
        parts.push(<span key={keyIndex++} style={currentStyle}>{segment}</span>);
      } else {
        parts.push(segment);
      }
    }

    // Update style based on ANSI code
    const code = parseInt(match[1], 10);
    if (code === 0) {
      currentStyle = {};
    } else if (colorMap[code]) {
      currentStyle = { ...currentStyle, ...colorMap[code] };
    }

    lastIndex = match.index + match[0].length;
  }

  // Add remaining text
  if (lastIndex < text.length) {
    const segment = text.slice(lastIndex);
    if (Object.keys(currentStyle).length > 0) {
      parts.push(<span key={keyIndex++} style={currentStyle}>{segment}</span>);
    } else {
      parts.push(segment);
    }
  }

  return parts.length > 0 ? parts : [text];
}

const AVAILABLE_COMMANDS = [
  'nthlayer drift',
  'nthlayer validate-slo',
  'nthlayer deps',
  'nthlayer blast-radius',
  'nthlayer portfolio',
  'nthlayer lint',
  'help',
  'clear',
];

export function Terminal({ onCommand, suggestions = [] }: TerminalProps) {
  const [input, setInput] = useState('');
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [commandHistory, setCommandHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [isProcessing, setIsProcessing] = useState(false);
  const [tabCompletions, setTabCompletions] = useState<string[]>([]);
  const [tabIndex, setTabIndex] = useState(0);

  const inputRef = useRef<HTMLInputElement>(null);
  const outputRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom when history changes
  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [history, isProcessing]);

  // Focus input on mount and click
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleContainerClick = () => {
    inputRef.current?.focus();
  };

  const executeCommand = async (cmd: string) => {
    if (!cmd.trim()) return;

    setIsProcessing(true);
    setCommandHistory((prev) => [...prev, cmd]);
    setHistoryIndex(-1);

    const result = onCommand(cmd);

    // Simulate processing delay
    if (result.delay && result.delay > 0) {
      await new Promise((resolve) => setTimeout(resolve, result.delay));
    }

    if (result.output === '__CLEAR__') {
      setHistory([]);
    } else {
      setHistory((prev) => [
        ...prev,
        { command: cmd, output: result.output, isError: result.isError },
      ]);
    }

    setIsProcessing(false);
    setInput('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    // Clear tab completions on any key except Tab
    if (e.key !== 'Tab') {
      setTabCompletions([]);
      setTabIndex(0);
    }

    if (e.key === 'Enter') {
      e.preventDefault();
      executeCommand(input);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (commandHistory.length > 0) {
        const newIndex = historyIndex < commandHistory.length - 1 ? historyIndex + 1 : historyIndex;
        setHistoryIndex(newIndex);
        setInput(commandHistory[commandHistory.length - 1 - newIndex] || '');
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIndex > 0) {
        const newIndex = historyIndex - 1;
        setHistoryIndex(newIndex);
        setInput(commandHistory[commandHistory.length - 1 - newIndex] || '');
      } else if (historyIndex === 0) {
        setHistoryIndex(-1);
        setInput('');
      }
    } else if (e.key === 'Tab') {
      e.preventDefault();

      if (tabCompletions.length > 0) {
        // Cycle through existing completions
        const nextIndex = (tabIndex + 1) % tabCompletions.length;
        setTabIndex(nextIndex);
        setInput(tabCompletions[nextIndex]);
      } else {
        // Find matching completions
        const matches = AVAILABLE_COMMANDS.filter((cmd) =>
          cmd.toLowerCase().startsWith(input.toLowerCase())
        );

        if (matches.length === 1) {
          setInput(matches[0] + ' ');
        } else if (matches.length > 1) {
          setTabCompletions(matches);
          setTabIndex(0);
          setInput(matches[0]);
        }
      }
    } else if (e.key === 'c' && e.ctrlKey) {
      e.preventDefault();
      setInput('');
      setIsProcessing(false);
    }
  };

  const welcomeMessage = useMemo(() => ({
    command: '',
    output: `NthLayer Interactive Demo v1.0.0
─────────────────────────────────
Type "help" for available commands.

Suggestions:
  • Edit the YAML on the left to configure a service
  • Run "nthlayer drift" to check error budget drift
  • Run "nthlayer validate-slo" to verify SLO targets
`,
    isError: false,
  }), []);

  const displayHistory = history.length === 0 ? [welcomeMessage] : history;

  return (
    <div
      className="h-full bg-gray-900 rounded-lg flex flex-col font-mono text-sm cursor-text"
      onClick={handleContainerClick}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2 bg-gray-800 rounded-t-lg border-b border-gray-700">
        <div className="flex gap-1.5">
          <div className="w-3 h-3 rounded-full bg-red-500" />
          <div className="w-3 h-3 rounded-full bg-yellow-500" />
          <div className="w-3 h-3 rounded-full bg-green-500" />
        </div>
        <span className="text-gray-400 text-xs ml-2">nthlayer terminal</span>
      </div>

      {/* Output area */}
      <div
        ref={outputRef}
        className="flex-1 overflow-y-auto p-4 terminal-scrollbar"
      >
        {displayHistory.map((entry, i) => (
          <div key={i} className="mb-4">
            {entry.command && (
              <div className="flex items-center text-gray-300">
                <span className="text-green-400 mr-2">$</span>
                <span>{entry.command}</span>
              </div>
            )}
            {entry.output && (
              <pre
                className={`mt-1 whitespace-pre-wrap ${
                  entry.isError ? 'text-red-400' : 'text-gray-300'
                }`}
              >
                {parseAnsi(entry.output)}
              </pre>
            )}
          </div>
        ))}

        {isProcessing && (
          <div className="flex items-center text-gray-400">
            <span className="animate-pulse">Processing...</span>
          </div>
        )}
      </div>

      {/* Suggestions bar */}
      {suggestions.length > 0 && (
        <div className="px-4 py-2 bg-gray-800 border-t border-gray-700">
          <div className="text-xs text-gray-500 mb-1">Try:</div>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((suggestion, i) => (
              <button
                key={i}
                className="px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors"
                onClick={() => {
                  setInput(suggestion);
                  inputRef.current?.focus();
                }}
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Tab completions */}
      {tabCompletions.length > 1 && (
        <div className="px-4 py-2 bg-gray-800 border-t border-gray-700">
          <div className="text-xs text-gray-500">
            Tab completions: {tabCompletions.map((c, i) => (
              <span key={i} className={i === tabIndex ? 'text-green-400' : 'text-gray-400'}>
                {c}{i < tabCompletions.length - 1 ? ', ' : ''}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Input area */}
      <div className="flex items-center px-4 py-3 bg-gray-800 rounded-b-lg border-t border-gray-700">
        <span className="text-green-400 mr-2">$</span>
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isProcessing}
          className="flex-1 bg-transparent text-gray-300 outline-none placeholder-gray-600"
          placeholder="Type a command..."
          autoComplete="off"
          spellCheck={false}
        />
      </div>
    </div>
  );
}
