// Mermaid configuration - loaded BEFORE mermaid.min.js
// This sets up the config that mermaid will use when it initializes

window.mermaidConfig = {
  startOnLoad: false,  // We'll trigger manually after icons load
  theme: 'dark',
  securityLevel: 'loose',
};

// Register icon packs after mermaid loads, then run
window.addEventListener('DOMContentLoaded', async function() {
  // Wait a tick for mermaid to be available
  await new Promise(r => setTimeout(r, 100));

  if (typeof mermaid === 'undefined') {
    console.error('Mermaid not available');
    return;
  }

  try {
    // Load icon packs
    console.log('Loading Iconify icon packs...');
    const [logosData, mdiData] = await Promise.all([
      fetch('https://unpkg.com/@iconify-json/logos@1/icons.json').then(r => r.json()),
      fetch('https://unpkg.com/@iconify-json/mdi@1/icons.json').then(r => r.json()),
    ]);
    console.log('Loaded', Object.keys(logosData.icons).length, 'logos icons');
    console.log('Loaded', Object.keys(mdiData.icons).length, 'mdi icons');

    // Register with mermaid
    mermaid.registerIconPacks([
      { name: logosData.prefix || 'logos', icons: logosData },
      { name: mdiData.prefix || 'mdi', icons: mdiData },
    ]);

    // Initialize mermaid
    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      securityLevel: 'loose',
    });

    // Run mermaid on all .mermaid elements
    console.log('Running mermaid...');
    await mermaid.run();
    console.log('Mermaid complete');

  } catch (err) {
    console.error('Mermaid setup error:', err);
  }
});
