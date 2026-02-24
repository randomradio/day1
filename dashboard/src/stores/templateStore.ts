import { create } from 'zustand';
import type { TemplateBranch } from '../types/schema';
import { api } from '../api/client';

interface TemplateStore {
  // State
  templates: TemplateBranch[];
  selectedTemplate: TemplateBranch | null;
  loading: boolean;
  error: string | null;

  // Actions
  fetchTemplates: (taskType?: string) => Promise<void>;
  createTemplate: (data: {
    name: string;
    source_branch: string;
    description?: string;
    applicable_task_types?: string[];
    tags?: string[];
  }) => Promise<TemplateBranch>;
  instantiateTemplate: (
    name: string,
    targetBranch: string,
    taskId?: string
  ) => Promise<void>;
  selectTemplate: (template: TemplateBranch | null) => void;
  clearError: () => void;
}

export const useTemplateStore = create<TemplateStore>((set, get) => ({
  templates: [],
  selectedTemplate: null,
  loading: false,
  error: null,

  fetchTemplates: async (taskType?: string) => {
    set({ loading: true, error: null });
    try {
      const data = await api.listTemplates(taskType);
      set({ templates: data.templates, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  createTemplate: async (data) => {
    set({ loading: true, error: null });
    try {
      const template = await api.createTemplate(data);
      await get().fetchTemplates();
      set({ loading: false });
      return template;
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
      throw e;
    }
  },

  instantiateTemplate: async (name, targetBranch, taskId) => {
    set({ loading: true, error: null });
    try {
      await api.instantiateTemplate(name, targetBranch, taskId);
      set({ loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  selectTemplate: (template) => set({ selectedTemplate: template }),

  clearError: () => set({ error: null }),
}));
