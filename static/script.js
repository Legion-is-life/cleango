// Format bytes to human readable size
function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Format date to local string
function formatDate(dateString) {
    if (!dateString) return 'Never';
    
    // Parse the ISO string as UTC
    const date = new Date(dateString);
    const now = new Date();
    
    // Ensure we're comparing in the same timezone
    const diffMs = now.getTime() - date.getTime();
    const diffSeconds = Math.floor(diffMs / 1000);
    
    if (diffSeconds < 5) return 'Just now';
    if (diffSeconds < 60) return `${diffSeconds} seconds ago`;
    if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)} minutes ago`;
    if (diffSeconds < 7200) return '1 hour ago';
    if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)} hours ago`;
    return date.toLocaleString();
}

// Fetch clean status from server
function updateCleanStatus() {
    fetch('/api/clean-status')
        .then(response => response.json())
        .then(data => {
            const timeElement = document.getElementById('clean-time');
            const typeElement = document.getElementById('clean-type');
            const resultElement = document.getElementById('clean-result');

            timeElement.textContent = data.timestamp ? formatDate(data.timestamp) : 'Never';
            
            if (data.type) {
                typeElement.textContent = `(${data.type})`;
                
                let resultText = '';
                let resultClass = '';
                
                if (data.result === 'success') {
                    resultText = data.torrents_removed > 0 
                        ? `Removed ${data.torrents_removed} torrents`
                        : 'No torrents needed cleaning';
                    resultClass = 'success';
                } else {
                    resultText = data.result.replace('error: ', '');
                    resultClass = 'error';
                }
                
                resultElement.textContent = resultText;
                resultElement.className = resultClass;
            } else {
                typeElement.textContent = '';
                resultElement.textContent = '';
                resultElement.className = '';
            }
        })
        .catch(error => console.error('Error fetching clean status:', error));
}

// Update version display
function updateVersion() {
    fetch('/api/version')
        .then(response => response.json())
        .then(data => {
            document.getElementById('app-version').textContent = data.version;
        })
        .catch(error => console.error('Error fetching version:', error));
}

// Update connection status
function updateConnectionStatus() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            const statusElement = document.getElementById('connection-status');
            statusElement.textContent = data.status === 'connected' ? 'Connected' : 'Disconnected';
            statusElement.className = `status ${data.status}`;
            document.getElementById('clean-button').disabled = data.status !== 'connected';
        })
        .catch(error => console.error('Error fetching status:', error));
}

// Update statistics
function updateStats() {
    fetch('/api/stats')
        .then(response => response.json())
        .then(data => {
            document.getElementById('total-deleted').textContent = data.total_deleted;
            document.getElementById('total-freed').textContent = formatBytes(data.total_size_freed);
        })
        .catch(error => console.error('Error fetching stats:', error));
}

// Pagination state
let currentPage = 1;
let totalPages = 1;
let rowsPerPage = 20;
let searchTimeout = null;

// Load and display torrents
function loadTorrents() {
    const searchTerm = document.getElementById('search-input').value.toLowerCase();
    const url = `/api/deleted?page=${currentPage}&per_page=${rowsPerPage}`;
    
    fetch(url)
        .then(response => response.json())
        .then(data => {
            displayTorrents(data.torrents);
            updatePagination(data);
        })
        .catch(error => console.error('Error fetching torrents:', error));
}

// Update pagination controls
function updatePagination(data) {
    totalPages = data.total_pages;
    currentPage = data.page;
    
    const prevButton = document.getElementById('prev-page');
    const nextButton = document.getElementById('next-page');
    const pageInfo = document.getElementById('page-info');
    
    prevButton.disabled = currentPage <= 1;
    nextButton.disabled = currentPage >= totalPages;
    pageInfo.textContent = `Page ${currentPage} of ${totalPages}`;
}

// Display torrents in table
function displayTorrents(torrents) {
    const tbody = document.getElementById('torrents-table');
    tbody.innerHTML = '';

    torrents.forEach(torrent => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${torrent.name}</td>
            <td>${formatBytes(torrent.size)}</td>
            <td>${torrent.tracker_message}</td>
            <td>${formatDate(torrent.deletion_date)}</td>
        `;
        tbody.appendChild(row);
    });
}

// Handle page navigation
function changePage(delta) {
    const newPage = currentPage + delta;
    if (newPage >= 1 && newPage <= totalPages) {
        currentPage = newPage;
        loadTorrents();
    }
}

// Clean torrents
function cleanTorrents() {
    const button = document.getElementById('clean-button');
    button.disabled = true;
    button.textContent = 'Cleaning...';

    fetch('/api/clean', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error('Error cleaning torrents:', data.error);
            } else {
                // Add a small delay to ensure database updates are complete
                setTimeout(() => {
                    updateStats();
                    loadTorrents();
                    updateCleanStatus();
                }, 1000);  // 1 second delay
            }
        })
        .catch(error => console.error('Error cleaning torrents:', error))
        .finally(() => {
            setTimeout(() => {
                button.disabled = false;
                button.textContent = 'Clean Torrents';
            }, 1000);
        });
}

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    // Initial loads
    updateVersion();
    updateConnectionStatus();
    updateStats();
    loadTorrents();
    updateCleanStatus();

    // Set up periodic checks
    setInterval(updateConnectionStatus, 5000);
    setInterval(updateCleanStatus, 5000);  // Fetch status from server every 5 seconds
    setInterval(() => {
        updateStats();
        loadTorrents();
    }, 5000);  // Refresh table and stats every 5 seconds

    // Clean button click handler
    document.getElementById('clean-button').addEventListener('click', cleanTorrents);

    // Pagination handlers
    document.getElementById('prev-page').addEventListener('click', () => changePage(-1));
    document.getElementById('next-page').addEventListener('click', () => changePage(1));

    // Rows per page handler
    document.getElementById('per-page-select').addEventListener('change', (e) => {
        rowsPerPage = parseInt(e.target.value);
        currentPage = 1;
        loadTorrents();
    });

    // Search input handler with debounce
    document.getElementById('search-input').addEventListener('input', () => {
        if (searchTimeout) {
            clearTimeout(searchTimeout);
        }
        searchTimeout = setTimeout(() => {
            currentPage = 1;
            loadTorrents();
        }, 300);
    });
});
