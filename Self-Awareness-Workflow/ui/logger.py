import logging
from datetime import datetime
from typing import Optional

class SystemLogger:
    def __init__(self):
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger('FaultDetectionSystem')

    def system_start(self):
        self.logger.info("="*50)
        self.logger.info("Fault Detection System Starting")
        self.logger.info("="*50)

    def system_stop(self):
        self.logger.info("="*50)
        self.logger.info("System Stopped")
        self.logger.info("="*50)

    def monitoring_status(self, window_start: int, window_end: int):
        self.logger.info(f"Monitoring window [{window_start}:{window_end}]")

    def anomaly_detected(self, index: int, confidence: float):
        self.logger.warning("!"*50)
        self.logger.warning(f"ANOMALY DETECTED at index {index}")
        self.logger.warning(f"Confidence: {confidence:.2f}%")
        self.logger.warning("!"*50)

    def diagnostic_result(self, fault_type: str, confidence: float):
        self.logger.info("-"*50)
        self.logger.info("Diagnostic Results:")
        self.logger.info(f"Fault Type: {fault_type}")
        self.logger.info(f"Confidence: {confidence:.2f}%")
        self.logger.info("-"*50)

    def prognosis_result(self, rul: float, timestamp: Optional[float] = None):
        self.logger.info("-"*50)
        self.logger.info("Prognosis Results:")
        self.logger.info(f"Remaining Useful Life: {rul:.2f} hours")
        if timestamp:
            time_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            self.logger.info(f"Timestamp: {time_str}")
        self.logger.info("-"*50)

    def error(self, component: str, error_msg: str):
        self.logger.error("!"*50)
        self.logger.error(f"Error in {component}:")
        self.logger.error(error_msg)
        self.logger.error("!"*50)

    def debug(self, msg: str):
        self.logger.debug(msg)