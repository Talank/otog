module_ids_we_are_considering=(1 12 14 24 25 27 28 29 30 31 37)
# module_ids_we_are_considering=(1 14 27 28 29 30 31 37)
# module_ids_we_are_considering=(14)

docker build -t dockerized-otog_n25 /home/tbaral/research/otog_icse/docker_project_vn25

for i in {1..40}
do
    if [[ ! " ${module_ids_we_are_considering[@]} " =~ " $i " ]]; then
        continue
    fi

    docker stop otog-container_n25_$i
    docker rm otog-container_n25_$i

    docker run --name otog-container_n25_$i --memory=8g --memory-swap=8g -e ID=$i dockerized-otog_n25

    mkdir -p /home/tbaral/research/otog_icse/results_n25/$i

    docker cp otog-container_n25_$i:/app/dataset /home/tbaral/research/otog_icse/results_n25/$i/
    docker cp otog-container_n25_$i:/app/test_list /home/tbaral/research/otog_icse/results_n25/$i/
    docker cp otog-container_n25_$i:/app/runs_n25 /home/tbaral/research/otog_icse/results_n25/$i/
    docker cp otog-container_n25_$i:/app/random_test_orders_n25 /home/tbaral/research/otog_icse/results_n25/$i/
done



# NOW run the same for n50
docker build -t dockerized-otog_n50 /home/tbaral/research/otog_icse/docker_project_vn50

for i in {1..40}
do
    if [[ ! " ${module_ids_we_are_considering[@]} " =~ " $i " ]]; then
        continue
    fi

    docker stop otog-container_n50_$i
    docker rm otog-container_n50_$i

    docker run --name otog-container_n50_$i --memory=8g --memory-swap=8g -e ID=$i dockerized-otog_n50

    mkdir -p /home/tbaral/research/otog_icse/results_n50/$i

    docker cp otog-container_n50_$i:/app/dataset /home/tbaral/research/otog_icse/results_n50/$i/
    docker cp otog-container_n50_$i:/app/test_list /home/tbaral/research/otog_icse/results_n50/$i/
    docker cp otog-container_n50_$i:/app/runs_n50 /home/tbaral/research/otog_icse/results_n50/$i/
    docker cp otog-container_n50_$i:/app/random_test_orders_n50 /home/tbaral/research/otog_icse/results_n50/$i/
done


#NOW run the same for n75
docker build -t dockerized-otog_n75 /home/tbaral/research/otog_icse/docker_project_vn75

for i in {1..40}
do
    if [[ ! " ${module_ids_we_are_considering[@]} " =~ " $i " ]]; then
        continue
    fi

    docker stop otog-container_n75_$i
    docker rm otog-container_n75_$i

    docker run --name otog-container_n75_$i --memory=8g --memory-swap=8g -e ID=$i dockerized-otog_n75

    mkdir -p /home/tbaral/research/otog_icse/results_n75/$i

    docker cp otog-container_n75_$i:/app/dataset /home/tbaral/research/otog_icse/results_n75/$i/
    docker cp otog-container_n75_$i:/app/test_list /home/tbaral/research/otog_icse/results_n75/$i/
    docker cp otog-container_n75_$i:/app/runs_n75 /home/tbaral/research/otog_icse/results_n75/$i/
    docker cp otog-container_n75_$i:/app/random_test_orders_n75 /home/tbaral/research/otog_icse/results_n75/$i/
done


#NOW run the same for n100
docker build -t dockerized-otog_n100 /home/tbaral/research/otog_icse/docker_project_vn100

for i in {1..40}
do
    if [[ ! " ${module_ids_we_are_considering[@]} " =~ " $i " ]]; then
        continue
    fi

    docker stop otog-container_n100_$i
    docker rm otog-container_n100_$i

    docker run --name otog-container_n100_$i --memory=8g --memory-swap=8g -e ID=$i dockerized-otog_n100

    mkdir -p /home/tbaral/research/otog_icse/results_n100/$i

    docker cp otog-container_n100_$i:/app/dataset /home/tbaral/research/otog_icse/results_n100/$i/
    docker cp otog-container_n100_$i:/app/test_list /home/tbaral/research/otog_icse/results_n100/$i/
    docker cp otog-container_n100_$i:/app/runs_n100 /home/tbaral/research/otog_icse/results_n100/$i/
    docker cp otog-container_n100_$i:/app/random_test_orders_n100 /home/tbaral/research/otog_icse/results_n100/$i/
done
