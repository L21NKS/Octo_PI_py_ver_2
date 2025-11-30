import os
from loguru import logger
def directory():
# Specify the directory name
    directory_name = "dataset"
    
    # Create the directory
    try:
        os.mkdir(directory_name)
        logger.success("The '{directory_name}' directory has been successfully created")
    except FileExistsError:
        logger.info("The directory '{directory_name}' already exists")
    except PermissionError:
        logger.critical("Permission denied: Unable to create '{directory_name}'")
    except Exception as e:
        logger.error(f"An error has occurred: {e}")
