import math
import torch

import torch.nn as nn
import torch.nn.functional as F
import torch.utils.model_zoo as model_zoo

from torch.autograd import Variable
from torchvision.models.resnet import BasicBlock, Bottleneck, ResNet


def classification_layer_init(tensor, pi=0.01):

    fill_constant = - math.log((1 - pi) / pi)

    if isinstance(tensor, Variable):
        classification_layer_init(tensor.data)

    return tensor.fill_(fill_constant)


model_urls = {
    'resnet18': 'https://download.pytorch.org/models/resnet18-5c106cde.pth',
    'resnet34': 'https://download.pytorch.org/models/resnet34-333f7ec4.pth',
    'resnet50': 'https://download.pytorch.org/models/resnet50-19c8e357.pth',
    'resnet101': 'https://download.pytorch.org/models/resnet101-5d3b4d8f.pth',
    'resnet152': 'https://download.pytorch.org/models/resnet152-b121ed2d.pth',
}


class BasicBlockFeatures(BasicBlock):

    def forward(self, x):

        if isinstance(x, tuple):
            x = x[0]

        residual = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        conv2_rep = out
        out = self.bn2(out)

        if self.downsample is not None:
            residual = self.downsample(x)

        out += residual
        out = self.relu(out)

        return out, conv2_rep


class BottleneckFeatures(Bottleneck):
    '''
    A Bottleneck that returns its last conv layer features.
    '''

    def forward(self, x):

        if isinstance(x, tuple):
            x = x[0]

        residual = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)
        out = self.relu(out)

        out = self.conv3(out)
        conv3_rep = out
        out = self.bn3(out)

        if self.downsample is not None:
            residual = self.downsample(x)

        out += residual
        out = self.relu(out)

        return out, conv3_rep


class ResNetFeatures(ResNet):
    '''
    A ResNet that returns features instead of classification.
    '''

    def forward(self, x):

        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)

        x, c2 = self.layer1(x)
        x, c3 = self.layer2(x)
        x, c4 = self.layer3(x)
        x, c5 = self.layer4(x)

        return c2, c3, c4, c5


def resnet18_features(pretrained=False, **kwargs):
    """Constructs a ResNet-18 model.
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
    """
    model = ResNetFeatures(BasicBlockFeatures, [2, 2, 2, 2], **kwargs)

    if pretrained:
        model.load_state_dict(model_zoo.load_url(model_urls['resnet18']))

    return model


def resnet34_features(pretrained=False, **kwargs):
    """Constructs a ResNet-34 model.
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
    """
    model = ResNetFeatures(BasicBlockFeatures, [3, 4, 6, 3], **kwargs)

    if pretrained:
        model.load_state_dict(model_zoo.load_url(model_urls['resnet34']))

    return model


def resnet50_features(pretrained=False, **kwargs):
    """Constructs a ResNet-50 model.
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
    """
    model = ResNetFeatures(BottleneckFeatures, [3, 4, 6, 3], **kwargs)

    if pretrained:
        model.load_state_dict(model_zoo.load_url(model_urls['resnet50']))

    return model


def resnet101_features(pretrained=False, **kwargs):
    """Constructs a ResNet-101 model.
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
    """
    model = ResNetFeatures(BottleneckFeatures, [3, 4, 23, 3], **kwargs)

    if pretrained:
        model.load_state_dict(model_zoo.load_url(model_urls['resnet101']))

    return model


def resnet152_features(pretrained=False, **kwargs):
    """Constructs a ResNet-152 model.
    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
    """
    model = ResNetFeatures(BottleneckFeatures, [3, 8, 36, 3], **kwargs)

    if pretrained:
        model.load_state_dict(model_zoo.load_url(model_urls['resnet152']))

    return model


class FeaturePyramid(nn.Module):
    def __init__(self, resnet):
        super(FeaturePyramid, self).__init__()

        self.resnet = resnet

        # based on resnet feature sizes
        # TODO: better names ):
        self.pyramid_transformation_3 = conv1x1(512, 256)
        self.pyramid_transformation_4 = conv1x1(1024, 256)
        self.pyramid_transformation_5 = conv1x1(2048, 256)

        self.pyramid_transformation_6 = conv3x3(2048, 256, padding=1, stride=2)
        self.pyramid_transformation_7 = conv3x3(256, 256, padding=1, stride=2)

        self.upsample_transform_1 = conv3x3(256, 256, padding=1)
        self.upsample_transform_2 = conv3x3(256, 256, padding=1)

    def forward(self, x):
        # don't need c2 as it is too large
        _, resnet_feature_3, resnet_feature_4, resnet_feature_5 = self.resnet(x)

        pyramid_feature_6 = self.pyramid_transformation_6(resnet_feature_5)
        pyramid_feature_7 = self.pyramid_transformation_7(F.relu(pyramid_feature_6))

        pyramid_feature_5 = self.pyramid_transformation_5(resnet_feature_5)

        pyramid_feature_4 = self.upsample_transform_1(
            torch.add(F.upsample(pyramid_feature_5, scale_factor=2),
                      self.pyramid_transformation_4(resnet_feature_4)))

        pyramid_feature_3 = self.upsample_transform_2(
            torch.add(F.upsample(pyramid_feature_4, scale_factor=2),
                      self.pyramid_transformation_3(resnet_feature_3)))

        return (pyramid_feature_3,
                pyramid_feature_4,
                pyramid_feature_5,
                pyramid_feature_6,
                pyramid_feature_7)


# resnet = resnet50_features()

# feature_pyramid = FeaturePyramid(resnet)
# a = Variable(torch.rand((1, 3, 224, 224)))
# print(feature_pyramid.forward(a))


class SubNet(nn.Module):

    def __init__(self, mode, anchors=9, classes=21, depth=4, activation=F.relu):
        super(SubNet, self).__init__()
        self.mode = mode
        self.anchors = anchors
        self.classes = classes
        self.depth = depth
        self.activation = activation

        self.subnet_base = nn.ModuleList([conv3x3(256, 256, padding=1)
                                          for _ in range(depth)])

        if mode == 'boxes':
            self.subnet_output = nn.Conv2d(256, 4 * self.anchors, kernel_size=3, padding=1)
        elif mode == 'classes':
            self.subnet_output = nn.Conv2d(256, self.classes * self.anchors, kernel_size=3, padding=1)

        classification_layer_init(self.subnet_output.weight.data)

    def forward(self, x):
        for layer in self.subnet_base:
            x = self.activation(layer(x))

        return F.sigmoid(self.subnet_output(x))


class RetinaNet(nn.Module):

    def __init__(self, num_of_classes=21):
        super(RetinaNet, self).__init__()
        self.resnet = resnet50_features(pretrained=True)
        self.feature_pyramid = FeaturePyramid(self.resnet)

        self.subnet_boxes = SubNet(mode='boxes')
        self.subnet_classes = SubNet(mode='classes')
        self.num_of_classes = num_of_classes

    def forward(self, x):

        boxes = []
        classes = []

        features = self.feature_pyramid(x)

        for feature in features:
            box_predictions = self.subnet_boxes(feature)
            class_predictions = self.subnet_classes(feature)
            box_predictions = box_predictions.permute(0, 2, 3, 1).contiguous().view(x.size(0), -1, 4)
            class_predictions = class_predictions.permute(0, 2, 3, 1).contiguous().view(x.size(0), -1, self.num_of_classes)

            boxes.append(box_predictions)
            classes.append(class_predictions)

        return torch.cat(boxes, 1), torch.cat(classes, 1)
