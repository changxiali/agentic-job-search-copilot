from job_workflow.models.v3 import AgentPlan, AgentTool, PlanStep, SearchGoal

SAFE_TOOL_WHITELIST = frozenset(AgentTool)


class SafePlanner:
    """按目标和当前状态自主选择下一步，但只能使用只读/内部写入工具。"""

    def create_plan(self, goal: SearchGoal, existing_leads: int = 0) -> AgentPlan:
        steps = [
            PlanStep(
                order=1,
                tool=AgentTool.search_jobs,
                reason="发现最近发布的公开岗位",
                parameters={"published_within_days": goal.published_within_days},
            ),
            PlanStep(order=2, tool=AgentTool.read_job_page, reason="读取岗位正文并保留来源"),
            PlanStep(order=3, tool=AgentTool.deduplicate_leads, reason="避免同一岗位重复进入 CRM"),
            PlanStep(
                order=4,
                tool=AgentTool.analyze_leads,
                reason="结合 JD 与 Candidate Profile 评估匹配",
            ),
            PlanStep(order=5, tool=AgentTool.rank_leads, reason="根据匹配、时效、来源质量排序"),
            PlanStep(
                order=6,
                tool=AgentTool.create_approval_proposals,
                reason="高匹配岗位只生成待审批提案，不投递或发消息",
            ),
            PlanStep(order=7, tool=AgentTool.refresh_analytics, reason="记录本轮结果和决策"),
        ]
        return self.validate(
            AgentPlan(
                goal_id=goal.goal_id,
                objective=f"为“{goal.title}”发现并评估公开岗位；现有线索 {existing_leads} 条",
                steps=steps,
            )
        )

    def validate(self, plan: AgentPlan) -> AgentPlan:
        for step in plan.steps:
            if step.tool not in SAFE_TOOL_WHITELIST:
                raise ValueError(f"计划包含非白名单工具：{step.tool}")
        return plan
