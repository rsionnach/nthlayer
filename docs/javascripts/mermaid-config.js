// Mermaid configuration with Iconify icon support for architecture-beta diagrams
// Uses 'mermaid-raw' class to prevent mkdocs-material auto-processing

window.mermaidConfig = {
  startOnLoad: false,
  theme: 'dark',
  securityLevel: 'loose',
};

window.addEventListener('DOMContentLoaded', async function() {
  await new Promise(r => setTimeout(r, 100));

  if (typeof mermaid === 'undefined') return;

  try {
    // Load and register Iconify icon packs (logos: and mdi:)
    const [logosData, mdiData] = await Promise.all([
      fetch('https://unpkg.com/@iconify-json/logos@1/icons.json').then(r => r.json()),
      fetch('https://unpkg.com/@iconify-json/mdi@1/icons.json').then(r => r.json()),
    ]);

    mermaid.registerIconPacks([
      { name: logosData.prefix || 'logos', icons: logosData },
      { name: mdiData.prefix || 'mdi', icons: mdiData },
    ]);

    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      securityLevel: 'loose',
    });

    // Transform pre.mermaid-raw > code to div.mermaid for rendering
    const codeBlocks = document.querySelectorAll('pre.mermaid-raw code');
    const nodes = [];

    codeBlocks.forEach((code) => {
      const content = code.textContent.trim();
      if (content) {
        const div = document.createElement('div');
        div.className = 'mermaid';
        div.textContent = content;
        code.closest('pre').replaceWith(div);
        nodes.push(div);
      }
    });

    if (nodes.length > 0) {
      await mermaid.run({ nodes });
    }
  } catch (err) {
    console.error('Mermaid initialization error:', err);
  }
});
