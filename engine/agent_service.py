"""
AgentService - Agent 门面层，HTTP Server 只依赖此接口

承接从 agent.py 移出的职责：知识管理、技能重载、报告文件写入、YAML 转换。
"""
import os
import threading
from contextlib import contextmanager
from typing import Optional

from engine.agent import TestAgent
from engine.config import AppConfig
from engine.plan_exporter import export_plan_zip, import_plan_zip
from engine.plan_store import PlanStore
from engine.skill_registry import SkillRegistry
from engine.intent_schema import validate_plan
from engine.workflow import TestWorkflow, WorkflowConflict
from knowledge.loader import _extract_station_name


class AgentService:
    """门面层，隔离 agent 内部结构对 HTTP 层的影响"""

    def __init__(
        self,
        agent: TestAgent,
        config: AppConfig,
        plan_store: PlanStore = None,
        skill_registry: SkillRegistry = None,
        yaml_runner=None,
        root_dir: str = "",
        planner_chat=None,
        workflow: TestWorkflow = None,
    ):
        self._agent = agent
        self._config = config
        self._plan_store = plan_store
        self._skill_registry = skill_registry
        self._yaml_runner = yaml_runner
        self._root_dir = root_dir
        self._planner_chat = planner_chat
        self._gen_id = 0  # 计划生成计数器，用于丢弃过期结果
        self._job_lock = threading.RLock()
        self._worker = None
        self._workflow = workflow or TestWorkflow(
            agent, os.path.join(root_dir, config.workflow.database_path),
            os.path.join(root_dir, config.reports.output_dir),
        )
        self._sync_agent(self._workflow.get_task())

    @contextmanager
    def _idle(self):
        with self._job_lock:
            if self._worker and self._worker.is_alive():
                raise WorkflowConflict("任务正在运行，请等待当前操作完成")
            yield

    def _sync_agent(self, task):
        if not task:
            return
        for key in ("plan", "results", "report", "report_id"):
            setattr(self._agent, key, task.get(key))
        if task.get("station"):
            if task["station"] != self._config.station:
                self._reload_skills(task["station"])
            self._agent.prompt_builder.knowledge_texts = list(task.get("knowledge_texts") or [])

    def _launch(self, operation):
        with self._idle():
            def run():
                try:
                    operation()
                except Exception as error:
                    self._agent.event_bus.emit({"type": "error", "message": str(error)})
                finally:
                    self._sync_agent(self._workflow.get_task())
            self._worker = threading.Thread(target=run, daemon=True)
            self._worker.start()

    def _check_task_id(self, task_id):
        if not task_id or task_id != self._workflow.current_id:
            raise WorkflowConflict("当前任务已变化，请重新加载任务")

    # ── 查询接口 ──

    def get_state(self) -> dict:
        task = self._workflow.get_task()
        if task:
            return task
        return {
            "state": self._agent.state.value,
            "plan": self._agent.plan,
            "results": self._agent.results,
            "report": self._agent.report,
            "report_id": self._agent.report_id,
            "task_id": None,
        }

    def list_tasks(self):
        return self._workflow.list_tasks()

    def get_task(self, task_id):
        return self._workflow.get_task(task_id)

    def load_task(self, task_id):
        with self._idle():
            self._workflow.select(task_id)
            task = self._workflow.get_task()
            self._sync_agent(task)
            return task

    def review_plan(self, task_id, revision, approved, comment=""):
        with self._idle():
            self._check_task_id(task_id)
            task = self._workflow.review(approved, revision, comment)
            self._sync_agent(task)
            return task

    def retry_report(self, task_id):
        with self._idle():
            self._check_task_id(task_id)
            self._workflow._expect({"report_failed"})
            self._launch(self._workflow.retry_report)

    def resume_diagnosis(self, task_id):
        with self._idle():
            self._check_task_id(task_id)
            self._workflow._expect({"diagnostic_failed"})
            self._launch(self._workflow.resume_diagnosis)

    def get_skills_summary(self) -> list[dict]:
        return self._skill_registry.summary()

    def get_report_content(self, report_id: str) -> Optional[dict]:
        report_path = os.path.join(
            self._root_dir, self._config.reports.output_dir, f"report_{report_id}.md"
        )
        if not os.path.exists(report_path):
            return None
        with open(report_path, "r", encoding="utf-8") as f:
            return {"report_id": report_id, "content": f.read()}

    def _cancel_generation(self):
        """取消正在进行的计划生成"""
        self._gen_id += 1
        if self._planner_chat:
            self._planner_chat.cancel()

    # ── 知识管理（从 agent.py 移入） ──

    def upload_knowledge(self, content: str) -> str:
        """上传知识文档：提取技能组 → 添加知识 → 重载技能，返回提示消息"""
        with self._idle():
            return self._upload_knowledge(content)

    def _upload_knowledge(self, content):
        self._workflow.clear_current()
        station_name = _extract_station_name(content)
        self._agent.prompt_builder.add_knowledge(content)
        self._cancel_generation()
        if station_name:
            self._config.station = station_name
            self._reload_skills(station_name)
        msg = '知识文档已上传'
        if station_name:
            msg += f'，已切换技能组: {station_name}'
        return msg

    def remove_knowledge(self, index: int):
        """删除指定索引的知识文档，取消正在进行的计划生成"""
        with self._idle():
            return self._remove_knowledge(index)

    def _remove_knowledge(self, index):
        self._workflow.clear_current()
        texts = self._agent.prompt_builder.knowledge_texts
        if 0 <= index < len(texts):
            texts.pop(index)
        self._cancel_generation()
        # 从剩余文档中重新检测技能组
        for text in texts:
            station_name = _extract_station_name(text)
            if station_name:
                self._config.station = station_name
                self._reload_skills(station_name)
                return

    def add_knowledge(self, content: str, station_name: str = None):
        """向后兼容：添加知识文本并可选重载技能"""
        self._agent.prompt_builder.add_knowledge(content)
        if station_name:
            self._reload_skills(station_name)

    def _reload_skills(self, station_name: str):
        """根据技能组名称重新加载技能"""
        if not station_name or os.path.basename(station_name) != station_name or station_name in (".", ".."):
            raise ValueError("技能组名称无效")
        root = os.path.normpath(self._root_dir)
        common_dir = os.path.join(root, 'skills', 'common')
        station_dir = os.path.join(root, 'skills', station_name)

        if not os.path.isdir(station_dir):
            print(f"[AgentService] 技能组目录不存在: {station_dir}，仅加载 common 技能")
            station_dir = None

        registry = SkillRegistry()
        dirs = [common_dir]
        if station_dir:
            dirs.append(station_dir)
        registry.discover(*dirs)

        # 更新所有持有 registry 引用的组件
        self._skill_registry = registry
        self._config.station = station_name
        self._agent.skill_registry = registry
        self._agent.prompt_builder.skill_registry = registry
        self._agent.planner.skill_registry = registry
        if self._yaml_runner:
            self._yaml_runner.skill_registry = registry

        skills = ', '.join(registry.list_skills().keys())
        print(f"[AgentService] 已重新加载技能({station_name}): {skills}")

    # ── 计划管理 ──

    def generate_plan(self, instruction: str = ""):
        """在后台线程生成测试计划，通过 WebSocket 推送进度和结果"""
        def generate():
            task = self._workflow.create(self._config.station,
                                         self._agent.prompt_builder.knowledge_texts,
                                         instruction=instruction)
            self._agent.event_bus.emit({"type": "plan_generated", "plan": task["plan"], "task": task})
        self._launch(generate)

    def update_plan(self, plan: dict, revision=None, task_id=None):
        """更新计划（已经是 YAML 格式，无需转换）"""
        with self._idle():
            self._check_task_id(task_id)
            task = self._workflow.edit(plan, revision)
            self._sync_agent(task)
            return task

    def save_plan(self, plan: dict, name: str = None, plan_id: str = None) -> str:
        """保存计划到磁盘，返回 plan_id。如果提供 plan_id 则覆盖更新，否则创建新计划"""
        if not self._plan_store:
            raise ValueError("计划存储未配置")

        if name:
            plan = dict(plan)
            plan["name"] = name

        plan = validate_plan(plan, self._skill_registry)

        knowledge_texts = self._agent.prompt_builder.knowledge_texts

        plan_id = self._plan_store.save(
            plan=plan,
            knowledge_texts=knowledge_texts,
            plan_id=plan_id,
        )
        return plan_id

    def list_saved_plans(self) -> list[dict]:
        if not self._plan_store:
            return []
        return self._plan_store.list_plans()

    def load_saved_plan(self, plan_id: str) -> dict:
        """加载已保存计划，恢复知识文档 + 技能"""
        with self._idle():
            station = self._config.station
            knowledge = list(self._agent.prompt_builder.knowledge_texts)
            try:
                return self._load_saved_plan(plan_id)
            except Exception:
                if self._config.station != station:
                    self._reload_skills(station)
                self._agent.prompt_builder.knowledge_texts = knowledge
                raise

    def _load_saved_plan(self, plan_id: str) -> dict:
        if not self._plan_store:
            raise ValueError("计划存储未配置")
        bundle = self._plan_store.load(plan_id)
        if not bundle:
            raise ValueError(f"计划 {plan_id} 不存在")

        plan = bundle.get("yaml_plan") or bundle["plan"]
        knowledge_texts = bundle.get("knowledge_texts") or []

        # 恢复知识文档
        self._agent.prompt_builder.knowledge_texts = list(knowledge_texts)

        # 从知识文档中提取技能组，重新加载对应技能
        for text in knowledge_texts:
            station_name = _extract_station_name(text)
            if station_name:
                self._reload_skills(station_name)
                break

        # Every loaded plan starts a new, unapproved task.
        with self._idle():
            task = self._workflow.create(self._config.station, knowledge_texts, plan=plan)
            self._sync_agent(task)

        return plan

    def delete_saved_plan(self, plan_id: str) -> bool:
        if not self._plan_store:
            return False
        return self._plan_store.delete(plan_id)

    # ── 导出 / 导入 ──

    def export_plan(self, plan: dict) -> tuple[str, bytes]:
        """导出计划为 zip，返回 (filename, zip_bytes)"""
        knowledge_texts = self._agent.prompt_builder.knowledge_texts
        station_name = self._config.station

        zip_bytes = export_plan_zip(
            plan=plan,
            knowledge_texts=knowledge_texts,
            station_name=station_name,
            root_dir=self._root_dir,
        )

        filename = (plan.get("name") or "测试计划") + ".zip"
        return filename, zip_bytes

    def import_plan(self, zip_bytes: bytes) -> dict:
        """导入 zip 包：解包技能到磁盘，恢复知识文档和计划，返回 plan dict"""
        with self._idle():
            return self._import_plan(zip_bytes)

    def _import_plan(self, zip_bytes: bytes) -> dict:
        result = import_plan_zip(zip_bytes, self._root_dir)

        station_name = result["station_name"]
        plan = result["plan"]
        knowledge_texts = result["knowledge_texts"]

        # 更新技能组名
        self._config.station = station_name

        # 恢复知识文档
        self._agent.prompt_builder.knowledge_texts = list(knowledge_texts)

        # 重新加载技能
        self._reload_skills(station_name)

        with self._idle():
            task = self._workflow.create(station_name, knowledge_texts, plan=plan)
            self._sync_agent(task)

        return plan

    def get_plan_variables(self) -> dict:
        """获取当前 YAML 计划的 variables 区块"""
        task = self._workflow.get_task()
        plan = task.get("plan") if task else self._agent.plan
        if plan and isinstance(plan, dict):
            return plan.get('variables', {})
        return {}

    def get_device_params(self) -> list[dict]:
        """
        获取需要用户填写的设备相关参数。
        只从当前已加载 skill 的 metadata.params.required 中提取，
        默认值从 YAML 计划 variables 中补充。
        """
        params = {}  # key -> {name, value, skill_description}

        # 1) 只从 skill required params 提取
        if self._skill_registry:
            for action, skill in self._skill_registry.list_skills().items():
                meta = skill.metadata
                required = meta.params.get('required', [])
                for param_name in required:
                    if param_name not in params:
                        params[param_name] = {
                            'name': param_name,
                            'value': '',
                            'description': meta.description,
                        }

        # 2) 用 YAML 计划 variables 中的同名值补充默认值
        yaml_vars = self.get_plan_variables()
        for key in params:
            if key in yaml_vars and yaml_vars[key] is not None:
                params[key]['value'] = yaml_vars[key]

        return list(params.values())

    # ── 测试执行 ──

    def start_test(self, variables: dict = None, task_id=None, revision=None):
        """在后台线程启动测试执行"""
        with self._idle():
            self._check_task_id(task_id)
            task = self._workflow.check_start(revision)
            if variables and any(task["plan"].get("variables", {}).get(key) != value
                                 for key, value in variables.items()):
                raise WorkflowConflict("运行参数已改变，请保存并重新审核")
            self._launch(lambda: self._workflow.start(revision))

    def stop_test(self):
        if self._agent.diagnostician:
            self._agent.diagnostician.cancel()
        runner = self._yaml_runner
        if runner:
            runner.stop()

    def pause_test(self):
        runner = self._yaml_runner
        if runner:
            runner.pause()

    def resume_test(self):
        runner = self._yaml_runner
        if runner:
            runner.resume()

    def get_test_control_state(self) -> dict:
        runner = self._yaml_runner
        if runner:
            return {"paused": runner.is_paused, "stopped": runner.is_stopped}
        return {"paused": False, "stopped": False}

    # ── 报告（文件写入从 reporter.py 移入） ──

    def generate_report(self) -> tuple[str, str]:
        task = self._workflow.get_task()
        if not task or not task.get("report"):
            raise WorkflowConflict("报告尚未生成，请查询任务状态或重试报告")
        return task["report_id"], task["report"]

    def reset(self):
        with self._idle():
            self._workflow.clear_current()
            self._agent.reset()

    def close(self):
        if self._worker:
            self._worker.join(timeout=10)
        if not self._worker or not self._worker.is_alive():
            self._workflow.close()
