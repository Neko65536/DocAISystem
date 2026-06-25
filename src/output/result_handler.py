"""
结果处理器
处理和保存任务执行结果
"""
from typing import Any, Dict, Optional
import json
from pathlib import Path
from dataclasses import dataclass

from utils.logger import get_logger
from utils.file_utils import FileUtils


@dataclass
class ResultData:
    """结果数据"""
    success: bool
    message: str
    data: Any = None
    metadata: Dict[str, Any] = None


class ResultHandler:
    """
    结果处理器
    处理、保存和输出任务执行结果
    """

    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        self.logger = get_logger(__name__)
        FileUtils.ensure_dir(output_dir)

    def save_result(
        self,
        result: ResultData,
        filename: Optional[str] = None
    ) -> str:
        """
        保存结果到文件

        Args:
            result: 结果数据
            filename: 文件名（可选，自动生成）

        Returns:
            str: 保存的文件路径
        """
        if not filename:
            filename = f"result_{Path(result.metadata.get('task_id', 'unknown'))}.json"

        output_path = Path(self.output_dir) / filename
        FileUtils.ensure_dir(str(output_path.parent))

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(
                    {
                        "success": result.success,
                        "message": result.message,
                        "data": result.data,
                        "metadata": result.metadata
                    },
                    f,
                    ensure_ascii=False,
                    indent=2
                )
            self.logger.info(f"结果已保存: {output_path}")
            return str(output_path)
        except Exception as e:
            self.logger.error(f"保存结果失败: {str(e)}")
            return ""

    def save_json(
        self,
        data: Any,
        filename: str
    ) -> str:
        """
        保存JSON数据

        Args:
            data: 要保存的数据
            filename: 文件名

        Returns:
            str: 保存的文件路径
        """
        output_path = Path(self.output_dir) / filename
        FileUtils.ensure_dir(str(output_path.parent))

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return str(output_path)
        except Exception as e:
            self.logger.error(f"保存JSON失败: {str(e)}")
            return ""

    def format_result(self, result: ResultData) -> str:
        """
        格式化结果为可读字符串

        Args:
            result: 结果数据

        Returns:
            str: 格式化后的字符串
        """
        if result.success:
            output = f"[成功] {result.message}\n"
            if result.data:
                output += f"\n数据:\n{json.dumps(result.data, ensure_ascii=False, indent=2)}"
        else:
            output = f"[失败] {result.message}"

        if result.metadata:
            output += f"\n\n元数据:\n{json.dumps(result.metadata, ensure_ascii=False, indent=2)}"

        return output
