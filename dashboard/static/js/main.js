// HALUNG Dashboard — Main JavaScript

(function() {
  'use strict';

  console.log('HALUNG Dashboard loaded');

  // Auto-refresh health status every 10 seconds (optional)
  function refreshStatus() {
    fetch('/api/health')
      .then(r => r.json())
      .then(d => console.log('Health:', d))
      .catch(e => console.error('Health check failed:', e));
  }

  // Start periodic refresh
  setInterval(refreshStatus, 10000);
})();
