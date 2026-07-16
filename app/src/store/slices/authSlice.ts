/**
 * 认证状态管理 Slice
 */

import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import type { User, ApiError } from '../../types';
import * as authApi from '../../api/auth';
import { clearTokens, getUserInfo, isAuthenticated } from '../../utils/tokenManager';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: ApiError | null;
  isInitialized: boolean;
}

const initialState: AuthState = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,
  isInitialized: false,
};

/**
 * 初始化认证状态（从本地存储恢复）
 */
export const initializeAuth = createAsyncThunk(
  'auth/initialize',
  async (_, { rejectWithValue }) => {
    try {
      const authenticated = await isAuthenticated();
      if (authenticated) {
        const user = await getUserInfo();
        if (user) {
          return { user, isAuthenticated: true };
        }
      }
      return { user: null, isAuthenticated: false };
    } catch (error) {
      return rejectWithValue(error);
    }
  }
);

/**
 * 邮箱注册
 */
export const registerWithEmail = createAsyncThunk(
  'auth/registerEmail',
  async (
    data: { email: string; password: string; full_name: string },
    { rejectWithValue }
  ) => {
    try {
      return await authApi.registerWithEmail(data);
    } catch (error) {
      return rejectWithValue(error);
    }
  }
);

/**
 * 邮箱登录
 */
export const loginWithEmail = createAsyncThunk(
  'auth/loginEmail',
  async (
    data: { email: string; password: string; remember_me?: boolean },
    { rejectWithValue }
  ) => {
    try {
      return await authApi.loginWithEmail(data);
    } catch (error) {
      return rejectWithValue(error);
    }
  }
);

/**
 * 社交登录
 */
export const loginWithSocial = createAsyncThunk(
  'auth/loginSocial',
  async (
    data: { provider: 'google' | 'apple' | 'facebook'; token: string },
    { rejectWithValue }
  ) => {
    try {
      return await authApi.loginWithSocial(data);
    } catch (error) {
      return rejectWithValue(error);
    }
  }
);

/**
 * 获取当前用户信息
 */
export const fetchCurrentUser = createAsyncThunk(
  'auth/fetchCurrentUser',
  async (_, { rejectWithValue }) => {
    try {
      return await authApi.getCurrentUser();
    } catch (error) {
      return rejectWithValue(error);
    }
  }
);

/**
 * 登出
 */
export const logout = createAsyncThunk('auth/logout', async () => {
  try {
    await authApi.logout();
    await clearTokens();
    return null;
  } catch (error) {
    // 即使API调用失败，也要清除本地Token
    await clearTokens();
    return null;
  }
});

/**
 * 删除账户
 */
export const deleteAccount = createAsyncThunk('auth/deleteAccount', async (_, { rejectWithValue }) => {
  try {
    await authApi.deleteAccount();
    await clearTokens();
    return null;
  } catch (error) {
    return rejectWithValue(error);
  }
});

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    clearError: (state) => {
      state.error = null;
    },
    setUser: (state, action: PayloadAction<User>) => {
      state.user = action.payload;
      state.isAuthenticated = true;
    },
  },
  extraReducers: (builder) => {
    // 初始化认证状态
    builder
      .addCase(initializeAuth.pending, (state) => {
        state.isLoading = true;
      })
      .addCase(initializeAuth.fulfilled, (state, action) => {
        state.user = action.payload.user;
        state.isAuthenticated = action.payload.isAuthenticated;
        state.isInitialized = true;
        state.isLoading = false;
      })
      .addCase(initializeAuth.rejected, (state) => {
        state.isInitialized = true;
        state.isLoading = false;
      });

    // 邮箱注册
    builder
      .addCase(registerWithEmail.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(registerWithEmail.fulfilled, (state) => {
        state.isLoading = false;
      })
      .addCase(registerWithEmail.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as ApiError;
      });

    // 邮箱登录
    builder
      .addCase(loginWithEmail.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(loginWithEmail.fulfilled, (state, action) => {
        state.user = action.payload.user;
        state.isAuthenticated = true;
        state.isLoading = false;
      })
      .addCase(loginWithEmail.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as ApiError;
      });

    // 社交登录
    builder
      .addCase(loginWithSocial.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(loginWithSocial.fulfilled, (state, action) => {
        state.user = action.payload.user;
        state.isAuthenticated = true;
        state.isLoading = false;
      })
      .addCase(loginWithSocial.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as ApiError;
      });

    // 获取当前用户
    builder
      .addCase(fetchCurrentUser.pending, (state) => {
        state.isLoading = true;
      })
      .addCase(fetchCurrentUser.fulfilled, (state, action) => {
        state.user = action.payload;
        state.isAuthenticated = true;
        state.isLoading = false;
      })
      .addCase(fetchCurrentUser.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as ApiError;
      });

    // 登出
    builder
      .addCase(logout.pending, (state) => {
        state.isLoading = true;
      })
      .addCase(logout.fulfilled, (state) => {
        state.user = null;
        state.isAuthenticated = false;
        state.isLoading = false;
        state.error = null;
      });

    // 删除账户
    builder
      .addCase(deleteAccount.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(deleteAccount.fulfilled, (state) => {
        state.user = null;
        state.isAuthenticated = false;
        state.isLoading = false;
        state.error = null;
      })
      .addCase(deleteAccount.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as ApiError;
      });
  },
});

export const { clearError, setUser } = authSlice.actions;
export default authSlice.reducer;
