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

    // Find pre.mermaid > code elements (mkdocs structure)
    const codeBlocks = document.querySelectorAll('pre.mermaid code');
    console.log('Found', codeBlocks.length, 'mermaid code blocks');

    // Debug: show what we found
    document.querySelectorAll('.mermaid').forEach((el, i) => {
      console.log('Element', i, el.tagName, 'text length:', el.textContent.length);
    });

    if (codeBlocks.length === 0) {
      console.log('No pre.mermaid>code found, checking for raw .mermaid divs...');
      const divs = document.querySelectorAll('div.mermaid');
      console.log('Found', divs.length, 'div.mermaid elements');
      divs.forEach((d, i) => console.log('Div', i, 'text:', d.textContent.substring(0, 50)));
    }

    // Transform pre>code to div for mermaid
    const nodes = [];
    codeBlocks.forEach((code) => {
      const content = code.textContent.trim();
      if (content) {
        const div = document.createElement('div');
        div.className = 'mermaid-diagram';
        div.textContent = content;
        code.closest('pre').replaceWith(div);
        nodes.push(div);
      }
    });

    console.log('Created', nodes.length, 'diagram divs');

    // Run mermaid only on our new divs
    if (nodes.length > 0) {
      await mermaid.run({ nodes });
    }
    console.log('Mermaid complete');

  } catch (err) {
    console.error('Mermaid error:', err);
  }
});
