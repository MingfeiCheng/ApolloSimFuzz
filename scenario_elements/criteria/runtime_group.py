import traceback

from loguru import logger
from typing import List

from .base import CriteriaBase
from .runtime_single import RuntimeSingleTest       
        
class RuntimeGroupTest(CriteriaBase):
    """
    A group of detectors, the criterion is successful when all the sub-criteria are successful
    """
    
    def __init__(
        self, 
        name: str = "RuntimeGroupTest",
        detectors: List[RuntimeSingleTest] = None,
        terminate_on_failure: bool = True,
    ):
        super(RuntimeGroupTest, self).__init__(name, None, None, terminate_on_failure)
                
        self.sub_criteria = detectors if detectors is not None else []
        self.sub_criteria_can_stop = [False for _ in range(len(self.sub_criteria))]
        
        self.st_detail = {}
        
    def tick(self, snapshot: dict):
                
        all_stop_count = 0
        for i, criterion in enumerate(self.sub_criteria):
            try:
                criterion.tick(snapshot)
            except Exception as e:
                logger.error(f"RuntimeGroupTest {self.name} update error in sub criterion {criterion.name}: {e}")
                traceback.print_exc()
                # return new_status
    
        for i, criterion in enumerate(self.sub_criteria):
            self.st_detail[criterion.actor_id] = criterion.st_detail
            if criterion.get_stop():
                all_stop_count += 1
        
        if all_stop_count == len(self.sub_criteria):
            all_stop = True
        else:
            all_stop = False
        
        if all_stop:
            logger.success(f"RuntimeGroupTest: {self.name} all sub criteria finished.")            
            logger.success(f"RuntimeGroupTest: {self.name} st_detail: {self.st_detail}")
            self._termination = True