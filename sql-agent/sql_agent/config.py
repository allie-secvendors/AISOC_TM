import os
from dotenv import dotenv_values


class ConfigProvider:
    # Define a class variable for allowed directories, defaulting to the current directory
    ALLOWED_DIRS = [os.path.abspath(os.getcwd())]

    @classmethod
    def set_allowed_dirs(cls, dirs):
        """Set the allowed directories for environment files"""
        cls.ALLOWED_DIRS = [os.path.abspath(d) for d in dirs]

    def __init__(self, env_path: str):
        # Validate and normalize the path
        if not env_path:
            raise ValueError("Environment file path cannot be empty")
        
        try:
            abs_path = os.path.abspath(env_path)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid path format: {env_path}") from e
        
        # Check if the file exists and is a file
        if not os.path.isfile(abs_path):
            raise ValueError(f"Path '{env_path}' does not exist or is not a file")
        
        # Get directory of the file
        file_dir = os.path.dirname(abs_path)
        
        # Check if the file's directory is within allowed directories
        is_allowed = False
        for allowed_dir in self.ALLOWED_DIRS:
            # Check if file_dir is equal to or a subdirectory of allowed_dir
            if file_dir == allowed_dir or file_dir.startswith(allowed_dir + os.sep):
                is_allowed = True
                break
        
        if not is_allowed:
            allowed_dirs_str = ", ".join(self.ALLOWED_DIRS)
            raise ValueError(f"Path '{env_path}' is not in allowed directories: {allowed_dirs_str}")
        
        # Load the config from the validated path
        self.config = dotenv_values(abs_path)

    def get_env(self, key: str):
        value = self.config.get(key)
        if value is None:
            raise ValueError(f"Environment variable '{key}' not defined")
        return value

    def get_config(self):
        return self.config


class AppConfig:
    def __init__(self, config_provider: ConfigProvider):
        self.OPENAI_API_KEY = config_provider.get_env('OPENAI_API_KEY')