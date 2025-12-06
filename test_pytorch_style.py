"""
PyTorch 스타일 데코레이터와 상속 테스트 파일
v4.2 기능 검증용
"""

import torch
import torch.nn as nn
from abc import ABC, abstractmethod


class BaseModule(nn.Module, ABC):
    """추상 베이스 모델 클래스"""
    
    def __init__(self):
        super().__init__()
    
    @abstractmethod
    def forward(self, x):
        pass


class MyTransformer(BaseModule):
    """Transformer 기반 모델
    
    데코레이터와 상속 정보가 GUI와 MCP에서 표시되어야 함
    """
    
    def __init__(self, hidden_dim=768):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.fc = nn.Linear(hidden_dim, hidden_dim)
    
    @torch.no_grad()
    def forward(self, x):
        """Forward pass with no gradient"""
        return self.fc(x)
    
    @staticmethod
    def create_model(hidden_dim=768):
        """정적 팩토리 메서드"""
        return MyTransformer(hidden_dim)
    
    @classmethod
    def from_pretrained(cls, path):
        """클래스 메서드 - 사전 학습된 모델 로드"""
        model = cls()
        # Load weights...
        return model


@torch.jit.script
def activation_function(x: torch.Tensor) -> torch.Tensor:
    """JIT 컴파일된 활성화 함수"""
    return torch.nn.functional.gelu(x)


class CustomOptimizer(torch.optim.Optimizer):
    """커스텀 옵티마이저
    
    torch.optim.Optimizer 상속
    """
    
    def __init__(self, params, lr=0.001):
        defaults = dict(lr=lr)
        super().__init__(params, defaults)
    
    @torch.no_grad()
    def step(self, closure=None):
        """최적화 스텝 수행"""
        loss = None
        if closure is not None:
            with torch.enable_grad():
                loss = closure()
        
        for group in self.param_groups:
            for p in group['params']:
                if p.grad is None:
                    continue
                # 커스텀 업데이트 로직
                p.data.add_(p.grad, alpha=-group['lr'])
        
        return loss
