"""
This file converts chainer parameters in npz format into tensorflow saved models.
"""

"""
This file implements a network that can learn to color sketches.
I first saw it at http://qiita.com/taizan/items/cf77fd37ec3a0bef5d9d
"""

# import gtk.gdk
from sys import stderr

import cv2
import scipy
import tensorflow as tf

import adv_net_util
import conv_util
import colorful_img_network_connected_rgbbin_util
import colorful_img_network_connected_util
import colorful_img_network_mod_util
import colorful_img_network_util
import sketches_util
import unet_both_util
import lnet_util
import unet_color_util
import unet_util
from general_util import *


try:
    image_summary = tf.image_summary
    scalar_summary = tf.scalar_summary
    histogram_summary = tf.histogram_summary
    merge_summary = tf.merge_summary
    SummaryWriter = tf.train.SummaryWriter
except:
    image_summary = tf.summary.image
    scalar_summary = tf.summary.scalar
    histogram_summary = tf.summary.histogram
    merge_summary = tf.summary.merge
    SummaryWriter = tf.summary.FileWriter


COLORFUL_IMG_NUM_BIN = 6  # Temporary

# TODO: change rtype
def convert(height, width, batch_size,
                       learning_rate, npz_file_dict, generator_network='unet',
                       use_adversarial_net = False, use_hint = False,
                       adv_net_weight=1.0, weight_decay_lambda=1e-5, sketch_reconstruct_weight = 10.0 , save_dir="model/",
                       input_mode = 'sketch', output_mode = 'rgb', use_cpu = False):
    """
    """

    input_shape = (1, height, width, 3)
    print('The input shape is: %s. Input mode is: %s. Output mode is: %s. Using %s generator network' % (str(input_shape),
          input_mode, output_mode, generator_network))

    # Define tensorflow placeholders and variables.
    with tf.Graph().as_default():
        input_sketches = tf.placeholder(tf.float32, shape=[batch_size, input_shape[1], input_shape[2], 1],
                                      name='input_sketches' if input_mode=='sketch' else 'input_bw')
        if use_hint:
            input_hint = tf.placeholder(tf.float32,
                                shape=[batch_size, input_shape[1], input_shape[2], 3], name='input_hint')
            input_concatenated = tf.concat(3, (input_sketches, input_hint))
            if generator_network == 'unet_color':
                assert input_mode == 'sketch'
                color_output = unet_color_util.net(input_concatenated)
                sketch_output = lnet_util.net((color_output - 128) / 128)  # This is the reconstructed sketch from the color output.
            else:
                # TODO: change the error message.
                raise AssertionError("Please input a valid generator network name. Possible options are: TODO. Got: %s"
                                     % (generator_network))
        else:
            if generator_network == 'unet_color':
                assert input_mode == 'sketch'
                color_output = unet_color_util.net(input_sketches)
                sketch_output = lnet_util.net((color_output - 128) / 128)  # This is the reconstructed sketch from the color output.
            else:
                raise AssertionError("Please input a valid generator network name. Possible options are: TODO. Got: %s"
                                     % (generator_network))

        chainer_to_tensorflow_var_dict = {'unet_color' : {}, 'lnet' : {}}
        for i in range(9):
            chainer_to_tensorflow_var_dict['unet_color']['c%d/W' % i] = 'conv_init_varsconv_down_%d/weights_init' % i
            chainer_to_tensorflow_var_dict['unet_color']['c%d/b' % i] = 'conv_init_varsconv_down_%d/bias_init' % i
            chainer_to_tensorflow_var_dict['unet_color']['bnc%d/beta' % i] = 'spatial_batch_normconv_down_%d/offset' % (i)
            chainer_to_tensorflow_var_dict['unet_color']['bnc%d/gamma' % i] = 'spatial_batch_normconv_down_%d/scale' % (i)
            chainer_to_tensorflow_var_dict['unet_color']['bnc%d/avg_mean' % i] = None  # 'spatial_batch_normconv_down_%d/mean' % (i)
            chainer_to_tensorflow_var_dict['unet_color']['bnc%d/avg_var' % i] = None  # 'spatial_batch_normconv_down_%d/variance' % (i)
            chainer_to_tensorflow_var_dict['unet_color']['bnc%d/N' % i] = None
        for i in range(9):
            chainer_to_tensorflow_var_dict['unet_color']['dc%d/W' % i] = 'conv_init_varsconv_up_%d/weights_init' % (8-i)
            chainer_to_tensorflow_var_dict['unet_color']['dc%d/b' % i] = 'conv_init_varsconv_up_%d/bias_init' % (8-i)
            chainer_to_tensorflow_var_dict['unet_color']['bnd%d/beta' % i] = 'spatial_batch_normconv_up_%d/offset' % (8-i)
            chainer_to_tensorflow_var_dict['unet_color']['bnd%d/gamma' % i] = 'spatial_batch_normconv_up_%d/scale' % (8-i)
            chainer_to_tensorflow_var_dict['unet_color']['bnd%d/avg_mean' % i] = None  # 'spatial_batch_normconv_up_%d/mean' % (8-i)
            chainer_to_tensorflow_var_dict['unet_color']['bnd%d/avg_var' % i] = None  # 'spatial_batch_normconv_up_%d/variance' % (8-i)
            chainer_to_tensorflow_var_dict['unet_color']['bnd%d/N' % i] = None # conv_tranpose_layerconv_up_%d/spatial_batch_normconv_up_%d/scale
        for i in range(9):
            chainer_to_tensorflow_var_dict['lnet']['c%d/W' % i] = 'conv_init_varsconv_down_%d/weights_init' % i
            chainer_to_tensorflow_var_dict['lnet']['c%d/b' % i] = 'conv_init_varsconv_down_%d/bias_init' % i
            chainer_to_tensorflow_var_dict['lnet']['bnc%d/beta' % i] = 'spatial_batch_normconv_down_%d/offset' % (i)
            chainer_to_tensorflow_var_dict['lnet']['bnc%d/gamma' % i] = 'spatial_batch_normconv_down_%d/scale' % (i)
            chainer_to_tensorflow_var_dict['lnet']['bnc%d/avg_mean' % i] = None  # 'spatial_batch_normconv_down_%d/mean' % (i)
            chainer_to_tensorflow_var_dict['lnet']['bnc%d/avg_var' % i] = None  # 'spatial_batch_normconv_down_%d/variance' % (i)
            chainer_to_tensorflow_var_dict['lnet']['bnc%d/N' % i] = None
        for i in range(9):
            chainer_to_tensorflow_var_dict['lnet']['dc%d/W' % i] = 'conv_init_varsconv_up_%d/weights_init' % (8-i)
            chainer_to_tensorflow_var_dict['lnet']['dc%d/b' % i] = 'conv_init_varsconv_up_%d/bias_init' % (8-i)
            chainer_to_tensorflow_var_dict['lnet']['bnd%d/beta' % i] = 'spatial_batch_normconv_up_%d/offset' % (8-i)
            chainer_to_tensorflow_var_dict['lnet']['bnd%d/gamma' % i] = 'spatial_batch_normconv_up_%d/scale' % (8-i)
            chainer_to_tensorflow_var_dict['lnet']['bnd%d/avg_mean' % i] = None  # 'spatial_batch_normconv_up_%d/mean' % (8-i)
            chainer_to_tensorflow_var_dict['lnet']['bnd%d/avg_var' % i] = None  # 'spatial_batch_normconv_up_%d/variance' % (8-i)
            chainer_to_tensorflow_var_dict['lnet']['bnd%d/N' % i] = None # conv_tranpose_layerconv_up_%d/spatial_batch_normconv_up_%d/scale

        learning_rate_init = tf.constant(learning_rate)
        learning_rate_var = tf.get_variable(name='learning_rate_var', trainable=False,
                                                initializer=learning_rate_init)
        color_expected_output = tf.placeholder(tf.float32,
                                         shape=[batch_size, input_shape[1], input_shape[2], 3],
                                         name='color_expected_output')
        # Use the mean difference loss. Used to use tf.nn.l2_loss. Don't know how big of a difference that makes.
        # color_loss_non_adv =tf.nn.l2_loss(color_output - color_expected_output) / batch_size
        color_loss_non_adv = tf.reduce_mean(tf.abs(color_output - color_expected_output))
        weight_decay_loss_non_adv = conv_util.weight_decay_loss(scope='unet') * weight_decay_lambda
        sketch_expected_output = lnet_util.net((color_expected_output - 128) / 128, reuse=True)
        sketch_reconstruct_loss_non_adv = tf.reduce_mean(tf.abs(sketch_output - sketch_expected_output)) * sketch_reconstruct_weight

        generator_loss_non_adv = color_loss_non_adv + weight_decay_loss_non_adv + sketch_reconstruct_loss_non_adv
        # TODO: add loss from sketch. That is, convert both generated and real colored image into sketches and compute their mean difference.

        # tv_loss = tv_weight * total_variation(image)

        generator_all_var = unet_util.get_net_all_variables()
        sketch_reconstruct_all_var = lnet_util.get_net_all_variables()


        if use_adversarial_net:
            adv_net_input = tf.placeholder(tf.float32,
                                             shape=[batch_size, input_shape[1], input_shape[2], 3], name='adv_net_input')
            adv_net_prediction_image_input = adv_net_util.net(adv_net_input)
            adv_net_prediction_generator_input = adv_net_util.net(color_output, reuse=True)
            adv_net_all_var = adv_net_util.get_net_all_variables()

            weight_decay_loss_adv= conv_util.weight_decay_loss(scope='adv_net') * weight_decay_lambda


            logits_from_i = adv_net_prediction_image_input
            logits_from_g = adv_net_prediction_generator_input

            # One represent labeling the image as coming from real image. Zero represent labeling it as generated.
            adv_loss_from_i = tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(logits_from_i, tf.ones([batch_size], dtype=tf.int64))) * adv_net_weight
            adv_loss_from_g = tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(logits_from_g, tf.zeros([batch_size], dtype=tf.int64))) * adv_net_weight

            adv_loss =  adv_loss_from_i + adv_loss_from_g + weight_decay_loss_adv
            generator_loss_through_adv = tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(logits_from_g, tf.ones([batch_size], dtype=tf.int64))) * adv_net_weight
            # Beta1 = 0.5 according to dcgan paper
            adv_train_step = tf.train.AdamOptimizer(learning_rate_var, beta1=0.5,
                                   beta2=0.999).minimize(adv_loss, var_list=adv_net_all_var)
            generator_train_step_through_adv = tf.train.AdamOptimizer(learning_rate_var, beta1=0.5,
                                   beta2=0.999).minimize(generator_loss_through_adv, var_list=generator_all_var)
            generator_train_step = tf.train.AdamOptimizer(learning_rate_var, beta1=0.9,
                                   beta2=0.999).minimize(generator_loss_non_adv)

            with tf.control_dependencies([generator_train_step_through_adv, generator_train_step]):
                generator_both_train = tf.no_op(name='generator_both_train')


            adv_loss_real_sum = scalar_summary("adv_loss_real", adv_loss_from_i)
            adv_loss_fake_sum = scalar_summary("adv_loss_fake", adv_loss_from_g)
            adv_loss_weight_decay_sum = scalar_summary("adv_loss_weight_decay", weight_decay_loss_adv)

            generator_loss_through_adv_sum = scalar_summary("g_loss_through_adv", generator_loss_through_adv)
            adv_loss_sum = scalar_summary("adv_loss", adv_loss)
            generator_loss_l2_sum = scalar_summary("generator_loss_non_adv", generator_loss_non_adv)
            generator_loss_weight_decay_sum = scalar_summary("generator_loss_weight_decay", weight_decay_loss_non_adv)
            sketch_reconstruct_loss_non_adv_sum = scalar_summary("sketch_reconstruct_loss_non_adv", sketch_reconstruct_loss_non_adv)


            g_sum = merge_summary([generator_loss_through_adv_sum, generator_loss_l2_sum, generator_loss_weight_decay_sum, sketch_reconstruct_loss_non_adv_sum])
            adv_sum = merge_summary([adv_loss_fake_sum, adv_loss_real_sum, adv_loss_weight_decay_sum, adv_loss_sum])
        else:
            # optimizer setup
            # Training using adam optimizer. Setting comes from https://arxiv.org/abs/1610.07629.
            generator_train_step = tf.train.AdamOptimizer(learning_rate_var, beta1=0.9,
                                   beta2=0.999).minimize(generator_loss_non_adv)
            generator_loss_l2_sum = scalar_summary("color_loss_non_adv", generator_loss_non_adv)
            generator_loss_weight_decay_sum = scalar_summary("generator_loss_weight_decay", weight_decay_loss_non_adv)
            sketch_reconstruct_loss_non_adv_sum = scalar_summary("sketch_reconstruct_loss_non_adv", sketch_reconstruct_loss_non_adv)
            g_sum = merge_summary([generator_loss_l2_sum, generator_loss_weight_decay_sum, sketch_reconstruct_loss_non_adv_sum])

        saver = tf.train.Saver()

        if use_cpu:
            config = tf.ConfigProto(
                device_count = {'GPU': 0}
            )
        else:
            config = None
        with tf.Session(config=config) as sess:
            if '0.12.0' in tf.__version__:
                all_vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES)
            else:
                all_vars = tf.get_collection(tf.GraphKeys.VARIABLES)

            chainer_to_tensorflow_var = generator_all_var + sketch_reconstruct_all_var
            if use_adversarial_net:
                chainer_to_tensorflow_var = chainer_to_tensorflow_var + adv_net_all_var
            var_not_saved = [item for item in all_vars if item not in (chainer_to_tensorflow_var)]
            sess.run(tf.initialize_variables(var_not_saved))
            for chainer_name, npz_file in npz_file_dict.iteritems():
                chainer_data = np.load(npz_file)
                chainer_var_names = sorted(chainer_data.files)
                current_chainer_to_tensorflow_var_dict = chainer_to_tensorflow_var_dict[chainer_name]
                current_possible_vars = sketch_reconstruct_all_var if chainer_name == 'lnet' else generator_all_var

                for chainer_var_name in chainer_var_names:
                    if chainer_var_name in current_chainer_to_tensorflow_var_dict:
                        tensorflow_var = None
                        tensorflow_var_name = current_chainer_to_tensorflow_var_dict[chainer_var_name]
                        if tensorflow_var_name == None:
                            continue
                        for possible_var in current_possible_vars:
                            if tensorflow_var_name in possible_var.name:
                                if tensorflow_var is not None:
                                    raise AssertionError('In %s, Duplicate variable %s and its corresponding variable %s and %s'
                                                         % (chainer_name, chainer_var_name, possible_var.name, tensorflow_var.name))
                                tensorflow_var = possible_var
                        if tensorflow_var is None:
                            raise AssertionError('In %s, Could not find variable %s and its corresponding variable %s'
                                                 %(chainer_name, chainer_var_name, tensorflow_var_name))
                        current_possible_vars.remove(tensorflow_var)

                        chainer_var = chainer_data[chainer_var_name]
                        try:
                            if len(chainer_var.shape) == 4:
                                # This works for both conv and deconv.
                                sess.run(tensorflow_var.assign(np.transpose(chainer_var,axes=(2,3,1,0))))
                            else:
                                sess.run(tensorflow_var.assign(chainer_var))
                        except ValueError as e:
                            raise ValueError('In %s, Error assigning variable %s. Error message %s' %(chainer_name, tensorflow_var.name, e))
                    else:
                        raise AssertionError('In %s, Unexpected variable %s' %(chainer_name, chainer_var_name))

                if len(current_possible_vars) != 0 :
                    raise AssertionError('In %s, Not all tensorflow variables initialized from chainer: %s' %(chainer_name, str(current_possible_vars)))
            saver.save(sess, save_dir + 'model.ckpt', global_step=0)


if __name__ == "__main__":
    save_dir = './model/chainer_converted/'
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    convert(128,128,1,0.0001,
            {'unet_color':"../PaintsChainer_py2/cgi-bin/paint_x2_unet/models/unet_128_standard",
             'lnet':"../PaintsChainer_py2/cgi-bin/paint_x2_unet/models/liner_f",},
            'unet_color',input_mode='sketch',use_hint=True, save_dir=save_dir)