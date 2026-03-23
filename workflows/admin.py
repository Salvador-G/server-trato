from django.contrib import admin
from .models import Workflow, WorkflowState, CustomerWorkflow, CustomerWorkflowHistory

@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "brand", "is_active", "sort_order")
    list_filter = ("brand", "is_active")
    search_fields = ("name", "code")

@admin.register(WorkflowState)
class WorkflowStateAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "workflow", "sort_order", "is_final")
    list_filter = ("workflow__brand", "is_final")

@admin.register(CustomerWorkflow)
class CustomerWorkflowAdmin(admin.ModelAdmin):
    list_display = ("customer", "workflow", "current_state", "assigned_to", "started_at", "finished_at")
    list_filter = ("workflow__brand", "workflow", "current_state")

@admin.register(CustomerWorkflowHistory)
class CustomerWorkflowHistoryAdmin(admin.ModelAdmin):
    list_display = ("customer_workflow", "state", "user", "changed_at")
    readonly_fields = ("changed_at",)