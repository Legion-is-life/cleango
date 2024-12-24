"""
app.py - A Flask application for cleaning torrents in qBittorrent.

This application connects to a qBittorrent client, monitors torrents, and removes those
that are unregistered or meet certain unwanted criteria. It provides a web interface
to manually trigger cleaning, view statuses, and display statistics.

Author: Your Name
Version: 0.0.1
"""

import os
import sqlite3
from datetime import datetime
import pytz
import threading
import time
import logging
from flask import Flask, render_template, jsonify, g, request
import qbittorrentapi

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Application version
APP_VERSION = "0.0.10"

# Clean status tracking
last_clean_status = {
    'timestamp': None,
    'type': None,  # 'manual' or 'scheduled'
    'result': None,  # success/error message
    'torrents_removed': 0
}

# Initialize Flask app
app = Flask(__name__)
app.config['VERSION'] = APP_VERSION

# Disable Flask's default logging
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.ERROR)
flask_logger = app.logger
flask_logger.setLevel(logging.ERROR)

# Database configuration
DATABASE = '/config/cleango.db'  # Hardcoded path in container

def get_db():
    """Get a connection to the SQLite database."""
    if 'db' not in g:
        g.db = sqlite3.connect(
            DATABASE,
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    """Close the database connection."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Initialize the database with the schema."""
    logger.info(f"Initializing database at {DATABASE}")
    
    # Create Flask application context
    with app.app_context():
        try:
            db = get_db()
            
            # Create the table directly
            db.execute('''
                CREATE TABLE IF NOT EXISTS deleted_torrents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    tracker_message TEXT NOT NULL,
                    deletion_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            db.commit()
            
            # Verify table exists
            count = db.execute('SELECT COUNT(*) FROM deleted_torrents').fetchone()[0]
            logger.info(f"Database initialized successfully. Current record count: {count}")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {str(e)}")
            raise

class TorrentCleaner:
    """Class for cleaning torrents from qBittorrent based on tracker messages."""

    def __init__(self, host: str, username: str, password: str):
        """
        Initialize the TorrentCleaner.

        Args:
            host (str): The qBittorrent host URL.
            username (str): The username for authentication.
            password (str): The password for authentication.
        """
        self.host = host
        self.username = username
        self.password = password
        self.client = self._initialize_client()
        self.connection_status = True

    def _initialize_client(self) -> qbittorrentapi.Client:
        """
        Initialize the qBittorrent client.

        Returns:
            qbittorrentapi.Client: The authenticated qBittorrent client.
        """
        try:
            client = qbittorrentapi.Client(
                host=self.host,
                username=self.username,
                password=self.password,
                VERIFY_WEBUI_CERTIFICATE=False
            )
            client.auth_log_in()
            return client
        except Exception as e:
            logger.error(f"Failed to initialize qBittorrent client: {e}")
            self.connection_status = False
            raise

    def _should_delete_torrent(self, tracker_msg: str) -> bool:
        """
        Determine if a torrent should be deleted based on tracker messages.

        Args:
            tracker_msg (str): The tracker message.

        Returns:
            bool: True if the torrent should be deleted, False otherwise.
        """
        unwanted_terms = ['unregistered', 'trump']
        return any(term in tracker_msg.lower() for term in unwanted_terms)

    def clean_torrents(self) -> list:
        """
        Clean torrents from the qBittorrent client.

        Returns:
            list: A list of dictionaries containing deleted torrent information.
        """
        deleted_torrents = []
        try:
            # Verify connection is active
            if not self.get_connection_status():
                raise ConnectionError("Not connected to qBittorrent")

            torrent_list = self.client.torrents_info()
            logger.info(f"Starting batch processing of {len(torrent_list)} torrents")

            for torrent in torrent_list:
                try:
                    # Get tracker message before attempting deletion
                    tracker_msg = next(
                        (t.msg for t in torrent.trackers if self._should_delete_torrent(t.msg)),
                        None
                    )
                    if tracker_msg and self._process_torrent(torrent, tracker_msg):
                        deleted_torrents.append({
                            'name': torrent.name,
                            'size_bytes': torrent.size,
                            'tracker_message': tracker_msg
                        })
                except Exception as e:
                    logger.error(f"Error processing torrent {torrent.hash}: {str(e)}")
                    continue

            if deleted_torrents:
                try:
                    self._save_deleted_torrents(deleted_torrents)
                except Exception as e:
                    logger.error(f"Error saving deleted torrents to database: {str(e)}")
                    # Continue even if DB save fails

            return deleted_torrents

        except qbittorrentapi.exceptions.APIConnectionError as e:
            logger.error(f"qBittorrent connection error: {str(e)}")
            self.connection_status = False
            raise
        except Exception as e:
            logger.error(f"Unexpected error during torrent cleaning: {str(e)}")
            self.connection_status = False
            raise

    def _process_torrent(self, torrent, tracker_msg: str) -> bool:
        """
        Process a single torrent and delete it.

        Args:
            torrent: The torrent object from qBittorrent API.
            tracker_msg: The tracker message that triggered deletion.

        Returns:
            bool: True if the torrent was deleted, False otherwise.
        """
        try:
            logger.info(f"Deleting torrent: {torrent.name} - {tracker_msg}")
            self.client.torrents_delete(delete_files=True, torrent_hashes=torrent.hash)
            logger.info(f"Successfully deleted torrent: {torrent.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete torrent {torrent.name}: {e}")
            return False

    def _save_deleted_torrents(self, deleted_torrents):
        """
        Save information about deleted torrents to the database.

        Args:
            deleted_torrents (list): List of deleted torrent information.
        """
        try:
            # Create a new app context for this operation
            ctx = app.app_context()
            ctx.push()
            try:
                db = get_db()
                for torrent in deleted_torrents:
                    db.execute(
                        'INSERT INTO deleted_torrents (name, size_bytes, tracker_message) VALUES (?, ?, ?)',
                        (torrent['name'], torrent['size_bytes'], torrent['tracker_message'])
                    )
                db.commit()
                logger.info(f"Batch operation complete: {len(deleted_torrents)} torrents were deleted and saved to database")
            finally:
                ctx.pop()
        except Exception as e:
            logger.error(f"Failed to save deleted torrents to database: {str(e)}")
            raise

    def get_connection_status(self) -> bool:
        """
        Check the connection status to the qBittorrent client.

        Returns:
            bool: True if connected, False otherwise.
        """
        try:
            self.client.app_version()
            self.connection_status = True
            return True
        except:
            self.connection_status = False
            return False

# Initialize cleaner with configuration from environment variables
HOST = os.getenv('QBITTORRENT_HOST')  # qBittorrent WebUI host:port
USERNAME = os.getenv('QBITTORRENT_USERNAME')  # qBittorrent WebUI username
PASSWORD = os.getenv('QBITTORRENT_PASSWORD')  # qBittorrent WebUI password

cleaner = None
try:
    if all([HOST, USERNAME, PASSWORD]):
        cleaner = TorrentCleaner(HOST, USERNAME, PASSWORD)
    else:
        logger.warning("Host, username, or password not set in environment variables.")
except Exception as e:
    logger.error(f"Failed to initialize TorrentCleaner: {e}")

@app.route('/')
def index():
    """Render the index page."""
    return render_template('index.html')

@app.route('/api/clean', methods=['POST'])
def clean():
    """API endpoint to manually trigger torrent cleaning."""
    global last_clean_status
    if not cleaner:
        return jsonify({'error': 'Cleaner not initialized'}), 500
    try:
        deleted = cleaner.clean_torrents()
        last_clean_status = {
            'timestamp': datetime.now(pytz.timezone('America/New_York')).isoformat(),
            'type': 'manual',
            'result': 'success',
            'torrents_removed': len(deleted)
        }
        return jsonify({'deleted': deleted})
    except Exception as e:
        last_clean_status = {
                'timestamp': datetime.now(pytz.timezone('America/New_York')).isoformat(),
            'type': 'manual',
            'result': f'error: {str(e)}',
            'torrents_removed': 0
        }
        return jsonify({'error': str(e)}), 500

@app.route('/api/status')
def status():
    """API endpoint to check the connection status to qBittorrent."""
    if not cleaner:
        return jsonify({'status': 'disconnected'})
    return jsonify({'status': 'connected' if cleaner.get_connection_status() else 'disconnected'})

@app.route('/api/deleted')
def get_deleted():
    """API endpoint to retrieve a list of deleted torrents."""
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    if per_page not in [20, 100]:
        per_page = 20

    offset = (page - 1) * per_page

    # Get total count
    total = db.execute('SELECT COUNT(*) as count FROM deleted_torrents').fetchone()['count']

    # Get paginated results
    torrents = db.execute(
        'SELECT name, size_bytes, tracker_message, deletion_date FROM deleted_torrents ORDER BY deletion_date DESC LIMIT ? OFFSET ?',
        (per_page, offset)
    ).fetchall()

    # Calculate total pages, minimum of 1
    total_pages = max(1, (total + per_page - 1) // per_page)

    return jsonify({
        'torrents': [{
            'name': row['name'],
            'size': row['size_bytes'],
            'tracker_message': row['tracker_message'],
            'deletion_date': row['deletion_date']
        } for row in torrents],
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages
    })

@app.route('/api/version')
def get_version():
    """API endpoint to get the application version."""
    return jsonify({'version': app.config['VERSION']})

@app.route('/api/stats')
def get_stats():
    """API endpoint to get statistics about deleted torrents."""
    db = get_db()
    stats = db.execute('''
        SELECT
            COUNT(*) as total_deleted,
            SUM(size_bytes) as total_size_freed
        FROM deleted_torrents
    ''').fetchone()

    return jsonify({
        'total_deleted': stats['total_deleted'],
        'total_size_freed': stats['total_size_freed'] or 0
    })

@app.route('/api/clean-status')
def get_clean_status():
    """API endpoint to get the status of the last cleaning operation."""
    return jsonify(last_clean_status)

# Register database close on app teardown
app.teardown_appcontext(close_db)

def run_periodic_clean():
    """Background task to clean torrents every hour."""
    global last_clean_status
    while True:
        try:
            if cleaner:
                logger.info("Starting automated cleaning process")
                # Create a new application context for the entire operation
                ctx = app.app_context()
                ctx.push()
                try:
                    deleted = cleaner.clean_torrents()
                    last_clean_status = {
                        'timestamp': datetime.now(pytz.timezone('America/New_York')).isoformat(),
                        'type': 'scheduled',
                        'result': 'success',
                        'torrents_removed': len(deleted)
                    }
                    logger.info(f"Automated cleaning completed. Deleted {len(deleted)} torrents.")
                finally:
                    # Always clean up the context and close the database connection
                    close_db()
                    ctx.pop()
            else:
                last_clean_status = {
                    'timestamp': datetime.now(pytz.timezone('America/New_York')).isoformat(),
                    'type': 'scheduled',
                    'result': 'error: Cleaner not initialized',
                    'torrents_removed': 0
                }
                logger.error("Automated cleaning failed: Cleaner not initialized")
        except Exception as e:
            last_clean_status = {
                'timestamp': datetime.now(pytz.timezone('America/New_York')).isoformat(),
                'type': 'scheduled',
                'result': f'error: {str(e)}',
                'torrents_removed': 0
            }
            logger.error(f"Error in automated cleaning: {e}")

        # Sleep for 1 hour
        time.sleep(3600)

if __name__ == '__main__':
    # Initialize the database
    init_db()

    # Start the background cleaning thread
    cleaning_thread = threading.Thread(target=run_periodic_clean, daemon=True)
    cleaning_thread.start()
    logger.info("Started background cleaning process")

    # Run the app
    app.run(host='0.0.0.0', port=5000)
