import sys
import subprocess
import requests
import keyring
from typing import Dict, Tuple, Optional, List
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QMessageBox,
    QLabel, QHBoxLayout, QDialog, QLineEdit, QInputDialog,
    QFormLayout, QDialogButtonBox, QTableWidget, QTableWidgetItem, QHeaderView , QFormLayout
)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QClipboard, QPixmap, QIcon
from PyQt5.QtGui import QPainter, QPainterPath
from dotenv import load_dotenv
import os
import webbrowser
import json
import logging

# Constants for GitHub OAuth
load_dotenv()
CLIENT_ID: str = os.getenv('CLIENT_ID', '')
GITHUB_API_URL: str = 'https://api.github.com/user'
OAUTH_URL: str = 'https://github.com/login/device/code'
ACCESS_TOKEN_URL: str = 'https://github.com/login/oauth/access_token'

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class ErrorBoundary:
    @staticmethod
    def handle_error(error: Exception, message: str) -> None:
        QMessageBox.critical(None, "Error", f"{message}: {str(error)}")

class GitHubOAuthDialog(QDialog):
    auth_completed = pyqtSignal(str)

    def __init__(self, oauth_url: str, user_code: str, expires_in: int, device_code: str, interval: int) -> None:
        super().__init__()
        self.oauth_url = oauth_url
        self.user_code = user_code
        self.expires_in = expires_in
        self.device_code = device_code
        self.interval = interval
        self.init_ui()

    def init_ui(self) -> None:
        self.setWindowTitle("GitHub OAuth")
        layout = QVBoxLayout()

        code_label = QLabel(f"User Code: {self.user_code}")
        layout.addWidget(code_label)

        copy_button = QPushButton("Copy Code")
        copy_button.clicked.connect(self.copy_code)
        layout.addWidget(copy_button)

        open_browser_button = QPushButton("Open GitHub Authorization Page")
        open_browser_button.clicked.connect(self.open_browser)
        layout.addWidget(open_browser_button)

        self.timer_label = QLabel(f"Code expires in: {self.expires_in} seconds")
        layout.addWidget(self.timer_label)

        self.retry_button = QPushButton("Generate New Code")
        self.retry_button.setEnabled(False)
        self.retry_button.clicked.connect(self.retry_oauth)
        layout.addWidget(self.retry_button)

        self.setLayout(layout)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.timer.start(1000)

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_for_token)
        self.poll_timer.start(self.interval * 1000)  # Use the initial interval

    def copy_code(self) -> None:
        clipboard: Optional[QClipboard] = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.user_code)
        else:
            ErrorBoundary.handle_error(Exception("Clipboard not available"), "Failed to copy code")

    def open_browser(self) -> None:
        try:
            webbrowser.open(self.oauth_url)
        except Exception as e:
            ErrorBoundary.handle_error(e, "Failed to open browser")

    def update_timer(self) -> None:
        self.expires_in -= 1
        if self.expires_in <= 0:
            self.timer.stop()
            self.retry_button.setEnabled(True)
        self.timer_label.setText(f"Code expires in: {self.expires_in} seconds")

    def retry_oauth(self) -> None:
        self.auth_completed.emit('')  # Signal to generate a new code

    def poll_for_token(self) -> None:
        try:
            response = requests.post(ACCESS_TOKEN_URL, data={
                'client_id': CLIENT_ID,
                'device_code': self.device_code,
                'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
            }, headers={'Accept': 'application/json'})
            
            data = response.json()
            
            if 'error' in data:
                if data['error'] == 'authorization_pending':
                    # Continue polling
                    return
                elif data['error'] == 'slow_down':
                    self.interval = data.get('interval', self.interval + 5)
                    self.poll_timer.setInterval(self.interval * 1000)
                    return
                elif data['error'] == 'expired_token':
                    QMessageBox.warning(self, "Error", "The device code has expired. Please try again.")
                    self.reject()
                elif data['error'] == 'access_denied':
                    QMessageBox.warning(self, "Error", "Access denied. The user cancelled the authorization.")
                    self.reject()
                else:
                    QMessageBox.warning(self, "Error", f"An error occurred: {data['error']}")
                    self.reject()
            elif 'access_token' in data:
                access_token = data['access_token']
                print(f"Access token received: {access_token}")
                self.auth_completed.emit(access_token)
                self.poll_timer.stop()
                self.accept()
        except requests.RequestException as e:
            ErrorBoundary.handle_error(e, "Error polling for access token")

class NameWidget(QWidget):
    def __init__(self, name: str, avatar_url: str, cache_dir: str) -> None:
        super().__init__()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0) # left, top, right, bottom
        self.label = QLabel()
        self.name_label = QLabel(name)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        # Try to load the image from cache
        image_path = os.path.join(cache_dir, f"{name}.png")
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
        else:
            # Try to download the image
            pixmap = QPixmap("assets/placeholder.png")  # Default to placeholder
            if avatar_url:
                try:
                    response = requests.get(avatar_url, timeout=5)
                    if response.status_code == 200:
                        image_data = response.content
                        pixmap = QPixmap()
                        pixmap.loadFromData(image_data)
                        # Save the image to cache
                        pixmap.save(image_path)
                except Exception as e:
                    logger.error(f"Failed to load avatar for {name}: {e}")
                    pass

        # Crop the image into a circular shape
        circular_pixmap = self.get_circular_pixmap(pixmap, 16)
        self.label.setPixmap(circular_pixmap)
        self.label.setFixedSize(16, 16)
        layout.addWidget(self.label)
        layout.addWidget(self.name_label)
        self.setLayout(layout)

    def get_circular_pixmap(self, pixmap: QPixmap, size: int) -> QPixmap:
        # Create a new circular pixmap
        circular_pixmap = QPixmap(size, size)
        circular_pixmap.fill(Qt.transparent)
        
        painter = QPainter(circular_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, size, size, pixmap.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        painter.end()

        return circular_pixmap

class GitHubProfileManager(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.profiles: Dict[str, Dict] = {}
        self.cache_dir = os.path.join(os.path.expanduser('~'), '.github_profile_manager', 'cache')
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        self.init_ui()
        self.resize(900, 600)  # Expand the width of the app
        self.load_profiles()
        current_profile = self.get_current_profile()
        if current_profile:
            self.update_current_profile(current_profile)
        self.update_profile_list()

    def init_ui(self) -> None:
        self.setWindowTitle("Easy Git Switcher")
        self.setWindowIcon(QIcon('assets/app_logo.ico'))  # Set your application logo here

        # Apply dark mode and GitHub Desktop styling
        self.setStyleSheet("""
            QWidget {
                background-color: #2d333b;
                font-family: "Segoe UI", sans-serif;
                color: #adbac7;
            }
            QPushButton {
                background-color: #2ea44f;
                border: 1px solid rgba(27,31,35,.15);
                border-radius: 4px;  /* Reduced border radius */
                color: white;
                padding: 4px 10px;  /* Reduced padding */
                font-size: 12px;  /* Smaller font size */
            }
            QPushButton:hover {
                background-color: #22863a;
            }
            QPushButton#deleteProfile {
                background-color: #d73a49;
                border: 1px solid #cb2431;
                color: white;
            }
            QPushButton#deleteProfile:hover {
                background-color: #b31d28;
            }
            QTableWidget {
                border: 1px solid #444c56;
                background-color: #22272e;
                color: #adbac7;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #2d333b;
                border: none;
                padding: 5px;
                font-weight: bold;
                font-size: 14px;
                color: #adbac7;
            }
            QTableWidget::item {
                border: none;
                padding: 5px;
                color: #adbac7;
            }
            QTableWidget::item:selected {
                background-color: #0366d6;
                color: white;
            }
            QLineEdit {
                background-color: #22272e;
                border: 1px solid #444c56;
                border-radius: 4px;
                padding: 4px;
                color: #adbac7;
            }
            QDialog {
                background-color: #2d333b;
            }
            QLabel {
                font-size: 14px;
                color: #adbac7;
            }
        """)

        layout = QVBoxLayout()
        
       

        button_layout = QHBoxLayout()
        add_account_btn = QPushButton("Add GitHub Account")
        add_account_btn.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                border: 1px solid #2ea44f;
                border-radius: 6px;
                padding: 5px 10px;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: #2ea44f;
            }
        """)
        add_account_btn.clicked.connect(self.add_account)
        button_layout.addWidget(add_account_btn)

        switch_account_btn = QPushButton("Switch Profile")
        switch_account_btn.clicked.connect(self.switch_profile)
        button_layout.addWidget(switch_account_btn)

        edit_profile_btn = QPushButton("Edit Profile")
        edit_profile_btn.clicked.connect(self.edit_profile)
        button_layout.addWidget(edit_profile_btn)

        delete_account_btn = QPushButton("Delete Selected Profile")
        delete_account_btn.setObjectName("deleteProfile")
        delete_account_btn.clicked.connect(self.delete_profile)
        button_layout.addWidget(delete_account_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        self.profile_table = QTableWidget()
        
        # Hide the vertical header
        self.profile_table.verticalHeader().setVisible(False)

        self.profile_table.setColumnCount(5)
        self.profile_table.setHorizontalHeaderLabels(["Name", "Username", "Email", "Tag", "Status"])
        self.profile_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.profile_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.profile_table)

        self.setLayout(layout)
        header = self.profile_table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.Stretch)            

    def load_profiles(self) -> None:
        try:
            # Load profiles from keyring
            keyring_profiles = self.load_keyring_profiles()
                        
            # Load profiles from git credential fill
            git_profile = self.get_git_credentials()
            
            # Merge profiles
            self.merge_profiles(keyring_profiles, git_profile)
            
            # Identify the current profile after merging
            current_profile = self.get_current_profile()
            if current_profile:
                self.update_current_profile(current_profile)
            else:
                # If no current profile is found, clear is_current for all profiles
                for profile in self.profiles.values():
                    profile['is_current'] = False
                self.save_profiles()
            
            self.update_profile_list()
        except Exception as e:
            ErrorBoundary.handle_error(e, "Failed to load profiles")

    def get_git_credentials(self) -> Dict[str, str]:
        try:
            result = subprocess.run(
                ['git', 'credential', 'fill'],
                input='url=https://github.com\n\n', 
                capture_output=True, text=True, check=True 
            )
            lines = result.stdout.strip().split('\n')
            credentials = {line.split('=', 1)[0].strip(): line.split('=', 1)[1].strip() 
                           for line in lines if '=' in line and 'stderr' not in line and line.split('=', 1)[0].strip() in ['username', 'password']}
            
            # Get user info from git config
            git_name, git_email = self.get_git_user_info()
            if 'username' in credentials and 'password' in credentials:
                credentials['name'] = git_name or ''
                credentials['email'] = git_email or ''
                return credentials
            
            return {}
    
        except subprocess.CalledProcessError as e:
            logger.error(f"Error retrieving git credentials: {e}")
            return {}
        
    def get_git_user_info(self) -> Tuple[str, str]:
        try:
            name = subprocess.run(['git', 'config', '--global', 'user.name'], capture_output=True, text=True, check=True).stdout.strip()
            email = subprocess.run(['git', 'config', '--global', 'user.email'], capture_output=True, text=True, check=True).stdout.strip()
            logger.debug(f"Git user info retrieved - Name: {name}, Email: {email}")
            return name, email
        except subprocess.CalledProcessError as e:
            logger.error(f"Error getting git user info: {e}")
            return '', ''

    def load_keyring_profiles(self) -> Dict[str, Dict]:
        keyring_profiles: Dict[str, Dict] = {}
        usernames = keyring.get_password('github', 'usernames')
        if usernames:
            for username in usernames.split(','):
                profile_data_str = keyring.get_password('github', username)
                if profile_data_str:
                    try:
                        profile_data = json.loads(profile_data_str)
                        keyring_profiles[username] = profile_data
                    except json.JSONDecodeError:
                        print(f"Warning: Invalid JSON data for user {username}")
        return keyring_profiles

    def merge_profiles(self, keyring_profiles: Dict[str, Dict], git_profile: Dict[str, str]) -> None:
        username = git_profile.get('username')
        if username and 'password' in git_profile:
            if username in keyring_profiles:
                # Update email and name if missing in keyring_profiles without overriding existing data
                if git_profile.get('email') and not keyring_profiles[username].get('email'):
                    keyring_profiles[username]['email'] = git_profile['email']
                if git_profile.get('name') and not keyring_profiles[username].get('name'):
                    keyring_profiles[username]['name'] = git_profile['name']
                # Do not override existing token
            else:
                # Add new profile
                keyring_profiles[username] = {
                    'token': git_profile['password'],
                    'name': git_profile.get('name') or username,
                    'email': git_profile.get('email') or '',
                    'tag': 'N/A'
                }
                logger.debug(f"Added new profile from git credentials: {username}")
        
        self.profiles = keyring_profiles
        self.save_profiles()

    def update_profile_list(self) -> None:
        logger.debug("Updating profile list")
        self.profile_table.setRowCount(0)
        for row, (username, profile) in enumerate(self.profiles.items()):
            self.profile_table.insertRow(row)
            is_current = profile.get('is_current', False)
            
            # Create Name widget with avatar displayed as rounded circular image
            name = profile.get('name', username)
            avatar_url = profile.get('avatar_url', '')
            name_widget = NameWidget(name, avatar_url, self.cache_dir)
            
            # Create other table items
            username_item = QTableWidgetItem(username)
            email_item = QTableWidgetItem(profile.get('email', ''))
            tag_item = QTableWidgetItem(profile.get('tag', 'N/A'))
            status = "Current" if is_current else "Not Current"
            status_item = QTableWidgetItem(status)
            
            # Add widgets/items to the table
            self.profile_table.setCellWidget(row, 0, name_widget)
            self.profile_table.setItem(row, 1, username_item)
            self.profile_table.setItem(row, 2, email_item)
            self.profile_table.setItem(row, 3, tag_item)
            self.profile_table.setItem(row, 4, status_item)
        
        header = self.profile_table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.Stretch)
        logger.debug("Profile list updated")
        
    def get_current_profile(self) -> Optional[str]:
        try:
            result_name = subprocess.run(['git', 'config', '--global', 'user.name'], capture_output=True, text=True)
            current_name = result_name.stdout.strip()

            result_email = subprocess.run(['git', 'config', '--global', 'user.email'], capture_output=True, text=True)
            current_email = result_email.stdout.strip()

            for username, profile in self.profiles.items():
                profile_name = profile.get('name', '')
                profile_email = profile.get('email', '')
                if profile_name == current_name and profile_email == current_email:
                    return username
            return None
        except subprocess.CalledProcessError:
            return None

    def add_account(self) -> None:
        try:
            oauth_data = self.generate_github_oauth()
            if oauth_data:
                logger.debug(f"OAuth data generated: {oauth_data}")
                dialog = GitHubOAuthDialog(*oauth_data)
                dialog.setStyleSheet("""
                      QDialog {
                          background-color: #2d333b;
                      }
                      QLabel {
                          font-size: 14px;
                          color: #adbac7;
                      }
                      QPushButton {
                          background-color: #2ea44f;
                          border-radius: 6px;
                          padding: 5px 10px;
                          color: #ffffff;
                      }
                      QPushButton:hover {
                          background-color: #22863a;
                      }
                      QLineEdit {
                          background-color: #22272e;
                          border: 1px solid #444c56;
                          border-radius: 4px;
                          padding: 4px;
                          color: #adbac7;
                      }
                      QDialogButtonBox {
                          background-color: #2d333b;
                          color: #adbac7;
                      }
                  """)
                dialog.auth_completed.connect(self.handle_oauth_completion)
                dialog.exec_()
            else:
                logger.error("Failed to generate OAuth data")
        except Exception as e:
            logger.exception("Failed to initiate GitHub OAuth")
            ErrorBoundary.handle_error(e, "Failed to initiate GitHub OAuth")

    def generate_github_oauth(self) -> Optional[Tuple[str, str, int, str, int]]:
        try:
            response = requests.post(OAUTH_URL, data={
                'client_id': CLIENT_ID,
                'scope': 'repo user'
            }, headers={'Accept': 'application/json'})

            if response.status_code == 200:
                data = response.json()
                return (
                    data['verification_uri'],
                    data['user_code'],
                    data['expires_in'],
                    data['device_code'],
                    data['interval']
                )
            else:
                raise Exception(f"GitHub API error: {response.status_code} - {response.text}")
        except requests.RequestException as e:
            ErrorBoundary.handle_error(e, "Network error")
        return None
    
    def handle_oauth_completion(self, token: str) -> None:
        logger.debug(f"OAuth completion handler called with token: {token[:5]}...")
        if token:
            try:
                username, name, email, avatar_url = self.get_github_user_info(token)
                print("username", username)
                if username:
                    if username not in self.profiles:
                        # Prompt for tag
                        tag, ok = QInputDialog.getText(self, "Add Tag", "Enter a tag for this profile:")
                        if ok:
                            # Use 'name' if available, else default to 'username'
                            profile_name = name if name else username
                            # Create new profile
                            new_profile = {
                                'token': token,
                                'name': profile_name,
                                'email': email or '',
                                'tag': tag,
                                'avatar_url': avatar_url
                            }
                            logger.debug(f"New profile created: {new_profile}")
                            # Add to profiles
                            self.profiles[username] = new_profile
                            self.save_profiles()
                            # If no current profile, set this as current
                            if not self.get_current_profile():
                                self.update_current_profile(username)
                                self.switch_to_profile(username)
                                self.update_profile_list()
                                QMessageBox.information(self, "Success", f"Added profile for {username} as current")
                            else:
                                self.update_profile_list()                            
                                QMessageBox.information(self, "Success", f"Added profile for {username}")
                            
                        else:
                            logger.debug("User cancelled tag input")
                    else:
                        logger.debug(f"Profile for {username} already exists")
                        QMessageBox.information(self, "Info", f"Profile for {username} already exists")
                else:
                    logger.debug("Username not obtained from GitHub API")
            except Exception as e:
                logger.exception("Failed to complete OAuth process")
                ErrorBoundary.handle_error(e, "Failed to complete OAuth process")
        else:
            logger.error("Failed to obtain access token")
            QMessageBox.warning(self, "Error", "Failed to obtain access token")

    def update_git_config(self, username: str, name: str, email: str, token: str) -> None:
        try:
            # Remove existing GitHub credentials
            self.remove_all_github_credentials()

            subprocess.run(['git', 'config', '--global', 'user.name', name], check=True)
            subprocess.run(['git', 'config', '--global', 'user.email', email], check=True)
            
            # Configure Git to use the credential helper
            subprocess.run(['git', 'config', '--global', 'credential.helper', 'manager-core'], check=True)
            
            # Store the GitHub token
            # Note: Approving credentials with empty username/password clears existing entries
            input_data = f"url=https://github.com\nusername={username}\npassword={token}\n\n"
            subprocess.run(['git', 'credential', 'approve'], input=input_data, text=True, check=True)
        
        except subprocess.CalledProcessError as e:
            ErrorBoundary.handle_error(e, "Failed to update Git config")

    def get_github_user_info(self, token: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        try:
            headers = {'Authorization': f'token {token}'}
            response = requests.get(GITHUB_API_URL, headers=headers)
            if response.status_code == 200:
                data = response.json()
                print("data", data)
                return data.get('login'), data.get('name'), data.get('email'), data.get('avatar_url')
            else:
                raise Exception(f"GitHub API error: {response.status_code}")
        except requests.RequestException as e:
            ErrorBoundary.handle_error(e, "Failed to retrieve GitHub user information")
        return None, None, None, None

    def save_profiles(self) -> None:
        try:
            keyring.set_password('github', 'usernames', ','.join(self.profiles.keys()))
            for username, profile in self.profiles.items():
                keyring.set_password('github', username, json.dumps(profile))
            logger.debug("Profiles saved successfully")
        except Exception as e:
            logger.exception("Failed to save profiles")
            ErrorBoundary.handle_error(e, "Failed to save profiles")

    def switch_profile(self) -> None:
        try:
            selected_row = self.profile_table.currentRow()
            if selected_row >= 0:
                username_item = self.profile_table.item(selected_row, 1)
                if username_item:
                    username = username_item.text()
                    profile = self.profiles.get(username)
                    if profile:
                        token = profile.get('token')
                        if token:
                            self.update_git_config(username, profile.get('name', username), profile.get('email', ''), token)
                            self.update_current_profile(username)
                            self.update_profile_list()
                            QMessageBox.information(self, "Success", f"Switched to profile: {username}")
                        else:
                            raise Exception("Token not found for the selected profile")
                    else:
                        raise Exception("Profile data is not available")
                else:
                    QMessageBox.warning(self, "Error", "No profile selected")
            else:
                QMessageBox.warning(self, "Error", "No profile selected")
        except Exception as e:
            ErrorBoundary.handle_error(e, "Failed to switch profile")

    def update_current_profile(self, new_current_username: str) -> None:
        for username, profile in self.profiles.items():
            profile['is_current'] = (username == new_current_username)
        self.save_profiles()

    def delete_profile(self) -> None:
        try:
            selected_row = self.profile_table.currentRow()
            if selected_row >= 0:
                username_item = self.profile_table.item(selected_row, 1)
                if username_item:
                    username = username_item.text()
                    if username in self.profiles:
                        is_current = self.profiles[username].get('is_current', False)
                        
                        if is_current:
                            # Prompt user to reconsider deleting the current profile
                            reply = QMessageBox.question(
                                self,
                                'Confirm Deletion',
                                f"The profile '{username}' is currently in use. Are you sure you want to delete it?",
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No
                            )
                            if reply == QMessageBox.No:
                                logger.debug("User cancelled deletion of current profile")
                                return  # Do not proceed with deletion

                        # Proceed with deletion
                        # Delete the profile from keyring
                        del self.profiles[username]
                        keyring.delete_password('github', username)
                        
                        # Remove from git credential store
                        self.remove_git_credential(username)
                        
                        self.profile_table.removeRow(selected_row)
                        self.save_profiles()
                        
                        # Handle current profile deletion
                        if is_current:
                            if self.profiles:
                                # Switch to the first available profile (sorted by username)
                                new_current = sorted(self.profiles.keys())[0]
                                self.switch_to_profile(new_current)
                            else:
                                # No profiles left, clear git config
                                self.clear_git_config()
                        
                        self.update_profile_list()
                        QMessageBox.information(self, "Success", f"Deleted profile: {username}")
                    else:
                        raise Exception(f"Profile {username} not found in stored profiles")
                else:
                    QMessageBox.warning(self, "Error", "No profile selected")
            else:
                QMessageBox.warning(self, "Error", "No profile selected")
        except Exception as e:
            ErrorBoundary.handle_error(e, f"Failed to delete profile: {str(e)}")

    def remove_git_credential(self, username: str) -> None:
        try:
            input_data = f"url=https://github.com\nusername={username}\n\n"
            subprocess.run(['git', 'credential', 'reject'], input=input_data, text=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error removing git credential: {e}")
            
    def switch_to_profile(self, username: str) -> None:
        profile = self.profiles.get(username)
        if profile:
            token = profile.get('token')
            if token:
                self.update_git_config(username, profile.get('name', username), profile.get('email', ''), token)
                self.update_current_profile(username)
                QMessageBox.information(self, "Profile Switch", f"Switched to profile: {username}")
            else:
                raise Exception("Token not found for the selected profile")
        else:
            raise Exception("Profile data is not available")

    def clear_git_config(self) -> None:
        try:
            subprocess.run(['git', 'config', '--global', '--unset', 'user.name'], check=True)
            subprocess.run(['git', 'config', '--global', '--unset', 'user.email'], check=True)
            subprocess.run(['git', 'config', '--global', '--unset', 'credential.helper'], check=True)
            
            # Remove all GitHub credentials from the git credential store
            self.remove_all_github_credentials()
            
            # Update the current profile status
            for profile in self.profiles.values():
                profile['is_current'] = False
            self.save_profiles()
            
            QMessageBox.information(self, "Info", "Git configuration cleared")
        except subprocess.CalledProcessError as e:
            ErrorBoundary.handle_error(e, "Failed to clear Git config")

    def remove_all_github_credentials(self) -> None:
        try:
            # Remove all credentials for GitHub from the credential manager
            subprocess.run(['git', 'credential', 'reject'], input="protocol=https\nhost=github.com\n\n", text=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error removing all GitHub credentials: {e}")

    def edit_profile(self) -> None:
        try:
            selected_row = self.profile_table.currentRow()
            if selected_row >= 0:
                username_item = self.profile_table.item(selected_row, 1)
                if username_item:
                    username = username_item.text()
                    profile = self.profiles.get(username)
                    if profile:
                        # Get current values
                        current_name = profile.get('name', '-')
                        current_email = profile.get('email', '-')
                        current_tag = profile.get('tag', 'N/A')
                        
                        # Open dialog to edit profile
                        dialog = QDialog(self)
                        dialog.setWindowTitle("Edit Profile")
                        layout = QFormLayout()
                        
                        name_edit = QLineEdit(current_name)
                        email_edit = QLineEdit(current_email)
                        tag_edit = QLineEdit(current_tag)
                        
                        layout.addRow("Name:", name_edit)
                        layout.addRow("Email:", email_edit)
                        layout.addRow("Tag:", tag_edit)
                        
                        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
                        button_box.accepted.connect(dialog.accept)
                        button_box.rejected.connect(dialog.reject)
                        layout.addWidget(button_box)
                        
                        dialog.setLayout(layout)
                        
                        if dialog.exec_() == QDialog.Accepted:
                            new_name = name_edit.text()
                            new_email = email_edit.text()
                            new_tag = tag_edit.text()
                            
                            # Update profile
                            profile['name'] = new_name
                            profile['email'] = new_email
                            profile['tag'] = new_tag
                            
                            self.profiles[username] = profile
                            self.save_profiles()
                            
                            # If this is the current profile, update git config
                            if profile.get('is_current', False):
                                token = profile.get('token')
                                if token:
                                    self.update_git_config(username, new_name, new_email, token)
                            
                            self.update_profile_list()
                            QMessageBox.information(self, "Success", f"Updated profile for {username}")
                    else:
                        QMessageBox.warning(self, "Error", "Profile data not found")
                else:
                    QMessageBox.warning(self, "Error", "No profile selected")
            else:
                QMessageBox.warning(self, "Error", "No profile selected")
        except Exception as e:
            ErrorBoundary.handle_error(e, "Failed to edit profile")

def main() -> None:
    app = QApplication(sys.argv)
    window = GitHubProfileManager()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
