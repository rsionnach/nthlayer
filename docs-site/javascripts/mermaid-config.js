// Mermaid configuration - loaded BEFORE mermaid.min.js

window.mermaidConfig = {
  startOnLoad: false,
  theme: 'dark',
  securityLevel: 'loose',
};

window.addEventListener('DOMContentLoaded', async function() {
  await new Promise(r => setTimeout(r, 100));

  if (typeof mermaid === 'undefined') {
    console.error('Mermaid not available');
    return;
  }

  try {
    // Load icon packs
    console.log('Loading icon packs...');
    const [logosData, mdiData] = await Promise.all([
      fetch('https://unpkg.com/@iconify-json/logos@1/icons.json').then(r => r.json()),
      fetch('https://unpkg.com/@iconify-json/mdi@1/icons.json').then(r => r.json()),
    ]);
    console.log('Icons loaded');

    mermaid.registerIconPacks([
      { name: logosData.prefix || 'logos', icons: logosData },
      { name: mdiData.prefix || 'mdi', icons: mdiData },
    ]);

    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      securityLevel: 'loose',
    });

    // Find pre.mermaid-raw > code elements (our custom class to avoid mkdocs auto-processing)
    const codeBlocks = document.querySelectorAll('pre.mermaid-raw code');
    console.log('Found', codeBlocks.length, 'mermaid-raw code blocks');

    // Transform pre>code to div for mermaid
    const nodes = [];
    codeBlocks.forEach((code, i) => {
      const content = code.textContent.trim();
      console.log('Block', i, 'content length:', content.length, 'preview:', content.substring(0, 60));

      if (content) {
        const div = document.createElement('div');
        div.className = 'mermaid';
        div.textContent = content;
        code.closest('pre').replaceWith(div);
        nodes.push(div);
      }
    });

    console.log('Created', nodes.length, 'diagram nodes');

    // Run mermaid on our nodes
    if (nodes.length > 0) {
      await mermaid.run({ nodes });
    }
    console.log('Mermaid complete');

  } catch (err) {
    console.error('Mermaid error:', err);
  }
});
