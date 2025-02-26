"""
Created on Wed Jan 17 08:05:11 2018

@author: Utku Ozbulak - github.com/utkuozbulak
"""
import torch
from torch.autograd import Variable
from torch.optim import SGD
import os

from misc_functions import get_example_params, recreate_image, save_image

import argparse
import numpy as np

class InvertedRepresentation():
    def __init__(self, model):
        self.model = model
        self.model.eval()
        if not os.path.exists('../generated'):
            os.makedirs('../generated')

    def alpha_norm(self, input_matrix, alpha):
        """
            Converts matrix to vector then calculates the alpha norm
        """
        alpha_norm = ((input_matrix.view(-1))**alpha).sum()
        return alpha_norm

    def total_variation_norm(self, input_matrix, beta):
        """
            Total variation norm is the second norm in the paper
            represented as R_V(x)
        """
        to_check = input_matrix[:, :-1, :-1]  # Trimmed: right - bottom
        one_bottom = input_matrix[:, 1:, :-1]  # Trimmed: top - right
        one_right = input_matrix[:, :-1, 1:]  # Trimmed: top - right
        total_variation = (((to_check - one_bottom)**2 +
                            (to_check - one_right)**2)**(beta/2)).sum()
        return total_variation

    def euclidian_loss(self, org_matrix, target_matrix):
        """
            Euclidian loss is the main loss function in the paper
            ||fi(x) - fi(x_0)||_2^2& / ||fi(x_0)||_2^2
        """
        distance_matrix = target_matrix - org_matrix
        euclidian_distance = self.alpha_norm(distance_matrix, 2)
        normalized_euclidian_distance = euclidian_distance / self.alpha_norm(org_matrix, 2)
        return normalized_euclidian_distance

    def get_output_from_specific_layer(self, x, layer_id):
        """
            Saves the output after a forward pass until nth layer
            This operation could be done with a forward hook too
            but this one is simpler (I think)
        """
        layer_output = None
        for index, layer in enumerate(self.model.features):
            x = layer(x)
            if str(index) == str(layer_id):
                layer_output = x[0]
                break
        return layer_output

    def generate_inverted_image_specific_layer(self, input_image, img_size, target_layer, file_name):
        # Generate a random image which we will optimize
        opt_img = Variable(1e-1 * torch.randn(1, 3, img_size, img_size), requires_grad=True)
        # Define optimizer for previously created image
        optimizer = SGD([opt_img], lr=1e4, momentum=0.9)
        # Get the output from the model after a forward pass until target_layer
        # with the input image (real image, NOT the randomly generated one)
        input_image_layer_output = \
            self.get_output_from_specific_layer(input_image, target_layer)

        # Alpha regularization parametrs
        # Parameter alpha, which is actually sixth norm
        alpha_reg_alpha = 6
        # The multiplier, lambda alpha
        alpha_reg_lambda = 1e-7

        # Total variation regularization parameters
        # Parameter beta, which is actually second norm
        tv_reg_beta = 2
        # The multiplier, lambda beta
        tv_reg_lambda = 1e-8
        
        for i in range(201):
            optimizer.zero_grad()
            # Get the output from the model after a forward pass until target_layer
            # with the generated image (randomly generated one, NOT the real image)
            output = self.get_output_from_specific_layer(opt_img, target_layer)
            # Calculate euclidian loss
            euc_loss = 1e-1 * self.euclidian_loss(input_image_layer_output.detach(), output)
            # Calculate alpha regularization
            reg_alpha = alpha_reg_lambda * self.alpha_norm(opt_img, alpha_reg_alpha)
            # Calculate total variation regularization
            reg_total_variation = tv_reg_lambda * self.total_variation_norm(opt_img,
                                                                            tv_reg_beta)
            # Sum all to optimize
            loss = euc_loss + reg_alpha + reg_total_variation
            # Step
            loss.backward()
            optimizer.step()
            # Generate image every 5 iterations
            if i % 5 == 0:
                print('Iteration:', str(i), 'Loss:', loss.data.numpy())
                recreated_im = recreate_image(opt_img)
                im_path = '../generated/Inv_Image_Layer_' + str(target_layer) + \
                    '_Iteration_' + str(i) + '.jpg'
                save_image(recreated_im, im_path)

            # Reduce learning rate every 40 iterations
            if i % 40 == 0:
                for param_group in optimizer.param_groups:
                    param_group['lr'] *= 1/10


if __name__ == '__main__':
    # Get params
    parser = argparse.ArgumentParser(description='Visualize Inverted Representation using Visdom.')
    parser.add_argument('model_dir', metavar='model-dir', help='Directory where model for dataset is to be found.', type=str, const=None, default=None)
    parser.add_argument('--batchnorm', help='Whether Batch Normalization was used.', action='store_true')
    parser.add_argument('-s', '--server', help='Server address. Default http://10.4.16.22 (i.e. node13).', nargs='?', type=str, const="http://10.4.16.22", default="http://10.4.16.22")
    parser.add_argument('-t', '--target', help='Target number. Default 0.', nargs='?', type=int, const=0, default=0)
    parser.add_argument('-i', '--imagesize', help='Image Size. Default 224.', nargs='?', type=int, const=224, default=224)
    parser.add_argument('-l', '--layer', help='Layer number. Default 4.', nargs='?', type=int, const=4, default=4)
    args = parser.parse_args()

    # Get params
    target_example = args.target
    (original_image, prep_img, target_class, file_name_to_export, pretrained_model) =\
        get_example_params(target_example, args.server, args.model_dir, args.batchnorm)

    inverted_representation = InvertedRepresentation(pretrained_model)
    image_size = args.imagesize  # width & height
    target_layer = args.layer
    inverted_representation.generate_inverted_image_specific_layer(prep_img,
                                                                   image_size,
                                                                   target_layer,
                                                                   file_name_to_export)
