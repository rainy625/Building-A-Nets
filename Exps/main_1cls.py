from __future__ import print_function
import os,time,cv2, sys, math
import tensorflow as tf
import tensorflow.contrib.slim as slim
import numpy as np
import time, datetime
import argparse
import random
import os, sys

import helpers
import utils

import matplotlib.pyplot as plt

sys.path.append("models")
from FC_DenseNet_Tiramisu import build_fc_densenet
from Encoder_Decoder import build_encoder_decoder
from Encoder_Decoder_Skip import build_encoder_decoder_skip
from RefineNet import build_refinenet
from HF_FCN import build_hf_fcn

def str2bool(v):
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

parser = argparse.ArgumentParser()
parser.add_argument('--num_epochs', type=int, default=300, help='Number of epochs to train for')
parser.add_argument('--is_training', type=str2bool, default=True, help='Whether we are training or testing')
parser.add_argument('--continue_training', type=str2bool, default=False, help='Whether to continue training from a checkpoint')
parser.add_argument('--dataset', type=str, default="CamVid", help='Dataset you are using.')
parser.add_argument('--crop_height', type=int, default=352, help='Height of input image to network')
parser.add_argument('--crop_width', type=int, default=480, help='Width of input image to network')
parser.add_argument('--batch_size', type=int, default=1, help='Width of input image to network')
parser.add_argument('--num_val_images', type=int, default=10, help='The number of images to used for validations')
parser.add_argument('--h_flip', type=str2bool, default=False, help='Whether to randomly flip the image horizontally for data augmentation')
parser.add_argument('--v_flip', type=str2bool, default=False, help='Whether to randomly flip the image vertically for data augmentation')
parser.add_argument('--brightness', type=str2bool, default=False, help='Whether to randomly change the image brightness for data augmentation')
parser.add_argument('--model', type=str, default="FC-DenseNet103", help='The model you are using. Currently supports:\
    FC-DenseNet56, FC-DenseNet67, FC-DenseNet103, FC-DenseNet158, Encoder-Decoder, Encoder-Decoder-Skip, RefineNet-Res101, RefineNet-Res152, HF-FCN, custom')
parser.add_argument('--gpu', type=int, default=0, help='Gpu device to use')
parser.add_argument('--balanced_weight', type=str2bool, default=False, help='whegher to use balanced weight')
args = parser.parse_args()


# Get a list of the training, validation, and testing file paths
def prepare_data(dataset_dir=args.dataset):
    train_input_names=[]
    train_output_names=[]
    val_input_names=[]
    val_output_names=[]
    test_input_names=[]
    test_output_names=[]
    for file in os.listdir(dataset_dir + "/train"):
        cwd = os.getcwd()
        train_input_names.append(cwd + "/" + dataset_dir + "/train/" + file)
    for file in os.listdir(dataset_dir + "/train_labels"):
        cwd = os.getcwd()
        train_output_names.append(cwd + "/" + dataset_dir + "/train_labels/" + file)
    for file in os.listdir(dataset_dir + "/val"):
        cwd = os.getcwd()
        val_input_names.append(cwd + "/" + dataset_dir + "/val/" + file)
    for file in os.listdir(dataset_dir + "/val_labels"):
        cwd = os.getcwd()
        val_output_names.append(cwd + "/" + dataset_dir + "/val_labels/" + file)
    for file in os.listdir(dataset_dir + "/test"):
        cwd = os.getcwd()
        test_input_names.append(cwd + "/" + dataset_dir + "/test/" + file)
    for file in os.listdir(dataset_dir + "/test_labels"):
        cwd = os.getcwd()
        test_output_names.append(cwd + "/" + dataset_dir + "/test_labels/" + file)
    return train_input_names,train_output_names, val_input_names, val_output_names, test_input_names, test_output_names


# Check if model is available
AVAILABLE_MODELS = ["FC-DenseNet56", "FC-DenseNet67", "FC-DenseNet103", "FC-DenseNet158", 
                    "Encoder-Decoder", "Encoder-Decoder-Skip", 
                    "RefineNet-Res101", "RefineNet-Res152", "HF-FCN", "custom"]
if args.model not in AVAILABLE_MODELS:
    print("Error: given model is not available. Try these:")
    print(AVAILABLE_MODELS)
    print("Now exiting ...")
    sys.exit()

# Load the data
print("Loading the data ...")
train_input_names,train_output_names, val_input_names, val_output_names, test_input_names, test_output_names = prepare_data()
if args.balanced_weight:
    balanced_weight = utils.median_frequency_balancing(args.dataset + "/train_labels/")

class_names_list = helpers.get_class_list(os.path.join(args.dataset, "class_list.txt"))
class_names_string = ""
for class_name in class_names_list:
    if not class_name == class_names_list[-1]:
        class_names_string = class_names_string + class_name + ", "
    else:
        class_names_string = class_names_string + class_name

# num_classes = len(class_names_list)
num_classes = 1

print("Preparing the model ...")
input = tf.placeholder(tf.float32,shape=[None,None,None,3])
output = tf.placeholder(tf.float32,shape=[None,None,None,num_classes])

with tf.device('/gpu:'+str(args.gpu)):
    input = tf.placeholder(tf.float32,shape=[None,None,None,3])
    output = tf.placeholder(tf.float32,shape=[None,None,None,num_classes])

    if args.model == "FC-DenseNet56" or args.model == "FC-DenseNet67" or args.model == "FC-DenseNet103" or args.model == "FC-DenseNet158":
        network = build_fc_densenet(input, preset_model = args.model, num_classes=num_classes)
    elif args.model == "RefineNet-Res101" or args.model == "RefineNet-Res152":
        network = build_refinenet(input, preset_model = args.model, num_classes=num_classes)
    elif args.model == "Encoder-Decoder":
        network = build_encoder_decoder(input, num_classes)
    elif args.model == "Encoder-Decoder-Skip":
        network = build_encoder_decoder_skip(input, num_classes)
    elif args.model == "HF-FCN":
        network = build_hf_fcn(input, preset_model ='FC-DenseNet103', num_classes=num_classes)
    elif args.model == "custom":
        network = build_custom(input, num_classes)

    # Compute your (unweighted) softmax cross entropy loss
    if not args.balanced_weight:
        loss = tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(logits=network, labels=output))
    else:
        loss = args.balanced_weight*tf.nn.softmax_cross_entropy_with_logits(logits=network, labels=output)

    opt = tf.train.RMSPropOptimizer(learning_rate=0.001, decay=0.995).minimize(loss, var_list=[var for var in tf.trainable_variables()])
config = tf.ConfigProto()
config.gpu_options.allow_growth = True
sess=tf.Session(config=config)

saver=tf.train.Saver(max_to_keep=1000)
sess.run(tf.global_variables_initializer())

utils.count_params()

model_checkpoint_name = "checkpoints2/latest_model.ckpt" #_" + args.model + "_" + args.dataset + "
if args.continue_training or not args.is_training:
    print('Loaded latest model checkpoint')
    saver.restore(sess, model_checkpoint_name)

avg_scores_per_epoch = []

if args.is_training:

    print("***** Begin training *****")

    avg_loss_per_epoch = []

    # Which validation images doe we want
    val_indices = []
    num_vals = min(args.num_val_images, len(val_input_names))
    for i in range(num_vals):
        ind = random.randint(0, len(val_input_names) - 1)
        val_indices.append(ind)

    # Do the training here
    for epoch in range(0, args.num_epochs):

        current_losses = []

        cnt=0
        id_list = np.random.permutation(len(train_input_names))
        num_iters = int(np.floor(len(id_list) / args.batch_size))

        for i in range(num_iters)[:1000]:
            st=time.time()
            
            input_image_batch = []
            output_image_batch = [] 

            # Collect a batch of images
            for j in range(args.batch_size):
                index = i*args.batch_size + j
                id = id_list[index]
                input_image = cv2.imread(train_input_names[id],-1)
                output_image = cv2.imread(train_output_names[id],-1)

                # Data augmentation
                input_image, output_image = utils.random_crop(input_image, output_image, args.crop_height, args.crop_width)

                if args.h_flip and random.randint(0,1):
                    input_image = cv2.flip(input_image, 1)
                    output_image = cv2.flip(output_image, 1)
                if args.v_flip and random.randint(0,1):
                    input_image = cv2.flip(input_image, 0)
                    output_image = cv2.flip(output_image, 0)
                if args.brightness:
                    factor = 1.0 + abs(random.gauss(mu=0.0, sigma=self.brightness))
                    if random.randint(0,1):
                        factor = 1.0/factor
                    table = np.array([((i / 255.0) ** factor) * 255 for i in np.arange(0, 256)]).astype(np.uint8)
                    image = cv2.LUT(image, table)


                # Prep the data. Make sure the labels are in one-hot format
                input_image = np.float32(input_image) / 255.0
                # output_image = np.float32(helpers.one_hot_it(label=output_image, num_classes=num_classes))
                output_image = np.float32(output_image[:,:, np.newaxis])

                input_image_batch.append(np.expand_dims(input_image, axis=0))
                output_image_batch.append(np.expand_dims(output_image, axis=0))

            # ***** THIS CAUSES A MEMORY LEAK AS NEW TENSORS KEEP GETTING CREATED *****
            # input_image = tf.image.crop_to_bounding_box(input_image, offset_height=0, offset_width=0, 
            #                                               target_height=args.crop_height, target_width=args.crop_width).eval(session=sess)
            # output_image = tf.image.crop_to_bounding_box(output_image, offset_height=0, offset_width=0, 
            #                                               target_height=args.crop_height, target_width=args.crop_width).eval(session=sess)
            # ***** THIS CAUSES A MEMORY LEAK AS NEW TENSORS KEEP GETTING CREATED *****

            # memory()
            
            if args.batch_size == 1:
                input_image_batch = input_image_batch[0]
                output_image_batch = output_image_batch[0]
            else:
                input_image_batch = np.squeeze(np.stack(input_image_batch, axis=1))
                output_image_batch = np.squeeze(np.stack(output_image_batch, axis=1))

            # Do the training
            _,current=sess.run([opt,loss],feed_dict={input:input_image_batch,output:output_image_batch})
            current_losses.append(current)
            cnt = cnt + args.batch_size
            if cnt % 20 == 0:
                string_print = "Epoch = %d Count = %d Current = %.2f Time = %.2f"%(epoch,cnt,current,time.time()-st)
                utils.LOG(string_print)

        mean_loss = np.mean(current_losses)
        avg_loss_per_epoch.append(mean_loss)
        
        # Create directories if needed
        if not os.path.isdir("%s/%04d"%("checkpoints2",epoch)):
            os.makedirs("%s/%04d"%("checkpoints2",epoch))

        saver.save(sess,model_checkpoint_name)
        saver.save(sess,"%s/%04d/model.ckpt"%("checkpoints2",epoch))


        target=open("%s/%04d/val_scores.txt"%("checkpoints2",epoch),'w')
        target.write("val_name, avg_accuracy, precision, recall, f1 score, mean iou %s\n" % (class_names_string))

        scores_list = []
        class_scores_list = []
        precision_list = []
        recall_list = []
        f1_list = []
        iou_list = []


        # Do the validation on a small set of validation images
        for ind in val_indices:
            
            input_image = np.expand_dims(np.float32(cv2.imread(val_input_names[ind],-1)[:args.crop_height, :args.crop_width]),axis=0)/255.0
            gt = cv2.imread(val_output_names[ind],-1)[:args.crop_height, :args.crop_width]

            st = time.time()

            output_image = sess.run(network,feed_dict={input:input_image})
            

            output_image = np.array(output_image[0,:,:,:])
            # output_image = helpers.reverse_one_hot(output_image)
            output_image = output_image>0.5
            out_eval_image = output_image[:,:,0]
            out_vis_image = helpers.colour_code_segmentation(output_image)

            accuracy = utils.compute_avg_accuracy(out_eval_image, gt)
            class_accuracies = utils.compute_class_accuracies(out_eval_image, gt, num_classes+1)
            prec = utils.precision(out_eval_image, gt)
            rec = utils.recall(out_eval_image, gt)
            f1 = utils.f1score(out_eval_image, gt)
            iou = utils.compute_mean_iou(out_eval_image, gt)
        
            file_name = utils.filepath_to_name(val_input_names[ind])
            target.write("%s, %f, %f, %f, %f, %f"%(file_name, accuracy, prec, rec, f1, iou))
            for item in class_accuracies:
                target.write(", %f"%(item))
            target.write("\n")

            scores_list.append(accuracy)
            class_scores_list.append(class_accuracies)
            precision_list.append(prec)
            recall_list.append(rec)
            f1_list.append(f1)
            iou_list.append(iou)
            
            gt = helpers.reverse_one_hot(helpers.one_hot_it(gt))
            gt = helpers.colour_code_segmentation(gt)
 
            file_name = os.path.basename(val_input_names[ind])
            file_name = os.path.splitext(file_name)[0]
            cv2.imwrite("%s/%04d/%s_pred.png"%("checkpoints2",epoch, file_name),np.uint8(out_vis_image))
            cv2.imwrite("%s/%04d/%s_gt.png"%("checkpoints2",epoch, file_name),np.uint8(gt))


        target.close()

        avg_score = np.mean(scores_list)
        class_avg_scores = np.mean(class_scores_list, axis=0)
        avg_scores_per_epoch.append(avg_score)
        avg_precision = np.mean(precision_list)
        avg_recall = np.mean(recall_list)
        avg_f1 = np.mean(f1_list)
        avg_iou = np.mean(iou_list)

        print("\nAverage validation accuracy for epoch # %04d = %f"% (epoch, avg_score))
        print("Average per class validation accuracies for epoch # %04d:"% (epoch))
        for index, item in enumerate(class_avg_scores):
            print("%s = %f" % (class_names_list[index], item))
        print("Validation precision = ", avg_precision)
        print("Validation recall = ", avg_recall)
        print("Validation F1 score = ", avg_f1)
        print("Validation IoU score = ", avg_iou)

        scores_list = []

    fig = plt.figure(figsize=(11,8))
    ax1 = fig.add_subplot(111)

    
    ax1.plot(range(num_epochs), avg_scores_per_epoch)
    ax1.set_title("Average validation accuracy vs epochs")
    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("Avg. val. accuracy")


    plt.savefig('accuracy_vs_epochs.png')

    plt.clf()

    ax1 = fig.add_subplot(111)

    
    ax1.plot(range(num_epochs), avg_loss_per_epoch)
    ax1.set_title("Average loss vs epochs")
    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("Current loss")

    plt.savefig('loss_vs_epochs.png')

else:
    print("***** Begin testing *****")

    # Create directories if needed
    if not os.path.isdir("%s"%("Test")):
            os.makedirs("%s"%("Test"))

    target=open("%s/test_scores.txt"%("Test"),'w')
    target.write("test_name, avg_accuracy, precision, recall, f1 score, mean iou %s\n" % (class_names_string))
    scores_list = []
    class_scores_list = []
    precision_list = []
    recall_list = []
    f1_list = []
    iou_list = []

    # Run testing on ALL test images
    for ind in range(len(test_input_names)):
        sys.stdout.write("\rRunning test image %d / %d"%(ind+1, len(test_input_names)))
        sys.stdout.flush()

        input_image = np.expand_dims(np.float32(cv2.imread(test_input_names[ind],-1)[:args.crop_height, :args.crop_width]),axis=0)/255.0
        st = time.time()
        output_image = sess.run(network,feed_dict={input:input_image})
        

        gt = cv2.imread(test_output_names[ind],-1)[:args.crop_height, :args.crop_width]

        output_image = np.array(output_image[0,:,:,:])
        output_image = helpers.reverse_one_hot(output_image)
        out_eval_image = output_image[:,:,0]
        out_vis_image = helpers.colour_code_segmentation(output_image)

        accuracy = utils.compute_avg_accuracy(out_eval_image, gt)
        class_accuracies = utils.compute_class_accuracies(out_eval_image, gt)
        prec = utils.precision(out_eval_image, gt)
        rec = utils.recall(out_eval_image, gt)
        f1 = utils.f1score(out_eval_image, gt)
        iou = utils.compute_mean_iou(out_eval_image, gt)
    
        file_name = utils.filepath_to_name(test_input_names[ind])
        target.write("%s, %f, %f, %f, %f, %f"%(file_name, accuracy, prec, rec, f1, iou))
        for item in class_accuracies:
            target.write(", %f"%(item))
        target.write("\n")

        scores_list.append(accuracy)
        class_scores_list.append(class_accuracies)
        precision_list.append(prec)
        recall_list.append(rec)
        f1_list.append(f1)
        iou_list.append(iou)
    
        gt = helpers.reverse_one_hot(helpers.one_hot_it(gt))
        gt = helpers.colour_code_segmentation(gt)

        cv2.imwrite("%s/%s_pred.png"%("Test", file_name),np.uint8(out_vis_image))
        cv2.imwrite("%s/%s_gt.png"%("Test", file_name),np.uint8(gt))


    target.close()

    avg_score = np.mean(scores_list)
    class_avg_scores = np.mean(class_scores_list, axis=0)
    avg_precision = np.mean(precision_list)
    avg_recall = np.mean(recall_list)
    avg_f1 = np.mean(f1_list)
    avg_iou = np.mean(iou_list)
    print("Average test accuracy = ", avg_score)
    print("Average per class test accuracies = \n")
    for index, item in enumerate(class_avg_scores):
        print("%s = %f" % (class_names_list[index], item))
    print("Average precision = ", avg_precision)
    print("Average recall = ", avg_recall)
    print("Average F1 score = ", avg_f1)
    print("Average mean IoU score = ", avg_iou)

