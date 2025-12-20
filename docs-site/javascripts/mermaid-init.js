// Initialize Mermaid with Iconify icon packs for architecture diagrams

window.addEventListener('load', async function() {
  if (typeof mermaid === 'undefined') {
    console.error('Mermaid not loaded');
    return;
  }

  try {
    // 1. Pre-load icon packs (must complete before mermaid processes diagrams)
    console.log('Loading icon packs...');
    const [logosData, mdiData] = await Promise.all([
      fetch('https://unpkg.com/@iconify-json/logos@1/icons.json').then(r => r.json()),
      fetch('https://unpkg.com/@iconify-json/mdi@1/icons.json').then(r => r.json()),
    ]);
    console.log('Icon packs loaded:', Object.keys(logosData.icons).length, 'logos,', Object.keys(mdiData.icons).length, 'mdi');

    // 2. Register pre-loaded icon packs
    mermaid.registerIconPacks([
      { name: logosData.prefix || 'logos', icons: logosData },
      { name: mdiData.prefix || 'mdi', icons: mdiData },
    ]);
    console.log('Icon packs registered');

    // 3. Initialize mermaid
    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      securityLevel: 'loose',
    });

    // 4. Fix HTML-escaped content and prepare divs for mermaid
    const mermaidBlocks = document.querySelectorAll('pre.mermaid');
    console.log('Found', mermaidBlocks.length, 'mermaid blocks');

    mermaidBlocks.forEach((pre, index) => {
      const code = pre.querySelector('code');
      if (code) {
        const content = code.textContent;
        console.log('Block', index, ':', content.substring(0, 60).replace(/\n/g, ' '));

        const div = document.createElement('div');
        div.className = 'mermaid';
        div.textContent = content;
        pre.parentNode.replaceChild(div, pre);
      }
    });

    // 5. Run mermaid
    console.log('Running mermaid.run()...');
    await mermaid.run({ querySelector: '.mermaid' });
    console.log('Mermaid rendering complete');

  } catch (error) {
    console.error('Mermaid init error:', error);
  }
});
