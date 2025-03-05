module_id=$1
script_dir="/app/scripts"

referenced_sheet="$script_dir/../referenced_sheets/commit_n_25.csv"
project_path="$script_dir/../projects/v0/$module_id"
init_runs_base_dir="$script_dir/../runs_n25/init_runs/$module_id"
init_test_list="$script_dir/../test_list/$module_id.txt"
test_orders_base_dir="$script_dir/../random_test_orders_n25"
runs_base_dir="$script_dir/../runs_n25/random_runs/$module_id"
execution_time_record_dir="$script_dir/../runs_n25/execution_time_record"
mvn_instance_base_dir="$script_dir/../mvn_instances"
apache_zip_dir="$script_dir/apache-maven-3.6.3-bin.zip"

java_8_home="/usr/lib/jvm/java-8-openjdk-amd64"
java_11_home="/usr/lib/jvm/java-11-openjdk-amd64"
java_17_home="/usr/lib/jvm/java-17-openjdk-amd64"

num_of_orders=26
num_of_executions=3

while IFS=, read -r ID project_name module_name url sha commit_n_25; do
    if [ "$ID" == "$module_id" ]; then
        module_path="$project_path/$module_name"
        # sha_to_checkout=$commit_n_25
        sha_to_checkout=$sha
        module=$module_name
        break
    fi
done < $referenced_sheet


MVNINSTALLOPTIONS="-Djacoco.skip=true -Dmaven.javadoc.skip=true -Drat.skip=true -Dmaven.test.failure.ignore=true -fn -Dlicense.skip=true -Dcheckstyle.skip -Denforcer.skip=true -Dspotbugs.skip=true -Dfindbugs.skip=true -DfailIfNoTests=false -Ddependency-check.skip=true"

create_mvn_instance() {
    # remove the maven instance if it already exists
    if [ -d $mvn_instance_base_dir/$module_id ]; then
        echo "Removing existing maven instance for $module_id"
        echo "rm -rf $mvn_instance_base_dir/$module_id"
        rm -rf $mvn_instance_base_dir/$module_id
    fi

    echo "Creating maven instance for $module_id"
    mkdir -p $mvn_instance_base_dir/$module_id
    # wget https://archive.apache.org/dist/maven/maven-3/3.6.3/binaries/apache-maven-3.6.3-bin.zip into the mvn_instance_base_dir
    # wget https://archive.apache.org/dist/maven/maven-3/3.6.3/binaries/apache-maven-3.6.3-bin.zip -P $mvn_instance_base_dir/$module_id/
    cp $apache_zip_dir $mvn_instance_base_dir/$module_id/
    unzip $mvn_instance_base_dir/$module_id/apache-maven-3.6.3-bin.zip -d $mvn_instance_base_dir/$module_id/
    mv $mvn_instance_base_dir/$module_id/apache-maven-3.6.3 $mvn_instance_base_dir/$module_id/maven
    
    export M2_HOME=$mvn_instance_base_dir/$module_id/maven
    export PATH=$PATH:$M2_HOME/bin
    export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
    export PATH=$JAVA_HOME/bin:$PATH
}

setup_custom_surefire_on_mvn_instance() {
    echo "Setting up custom surefire on maven instance"
    git clone https://github.com/TestingResearchIllinois/maven-surefire.git $mvn_instance_base_dir/$module_id/maven-surefire
    cd $mvn_instance_base_dir/$module_id/maven-surefire
    mvn install -DskipTests -Drat.skip -Denforcer.skip -Dcheckstyle.skip
    cp $mvn_instance_base_dir/$module_id/maven-surefire/surefire-changing-maven-extension/target/surefire-changing-maven-extension-1.0-SNAPSHOT.jar $mvn_instance_base_dir/$module_id/maven/lib/ext/
    cd -

    ls $mvn_instance_base_dir/$module_id/maven/lib/ext/
}

inject_plugin_management() {
  local pom_file="$1"
  if [[ ! -f "$pom_file" ]]; then
    echo "Error: File '$pom_file' not found." >&2
    return 1
  fi

  # Create a backup of the original pom.xml
  cp "$pom_file" "${pom_file}.bak"
  echo "Backup created at ${pom_file}.bak"

  # Use sed to insert the pluginManagement block before the closing </build> tag.
  # Note: On macOS you might need to change `sed -i` to `sed -i ''`.
  sed -i "/<\/build>/i\\
<pluginManagement>\\
  <plugins>\\
    <plugin>\\
      <groupId>org.apache.felix</groupId>\\
      <artifactId>maven-bundle-plugin</artifactId>\\
      <version>\2.5.0</version>\\
    </plugin>\\
  </plugins>\\
</pluginManagement>" "$pom_file"

  echo "Injected pluginManagement block into $pom_file"
}

fix_project_for_init_run() {
    echo "Fixing project for initial run"
    cd $project_path
    # git checkout $sha_to_checkout remove every unstagedchanges or whatever.. make sure the project is in the state of the commit_n_25
    git stash save "stash before checkout"
    git checkout $sha_to_checkout

    echo "Running the sed"
    whereis sed

    if [[ "$project_name" == "openpojo" ]]; then
        echo "Openpojo project, running the sed command to change the CredentialsRandomGenerator.java file"
        sed -i '70s/.*/return null;/' src/main/java/com/openpojo/random/generator/security/CredentialsRandomGenerator.java

    elif [[ "$project_name" == "Achilles" ]]; then
        echo "Achilles project, changing the version of the maven-surefire-plugin"
        ls | grep pom.xml
        sed -i 's~http://repo1.maven.org/maven2~https://repo1.maven.org/maven2~g' pom.xml
        find . -name "pom.xml" -type f -exec sed -i 's/6.0.1-SNAPSHOT/6.0.1/g' {} +
        inject_plugin_management pom.xml

    elif [[ "$project_name" == "spring-data-envers" ]]; then
        echo "Spring-data-envers project, changing the version of the spring-data-releasetrain"
        sed -i 's~2.2.0.BUILD-SNAPSHOT~2.2.0.RELEASE~g' pom.xml
    fi

    cd -
}

# run maven install command simply on the module
run_init_maven_test() {
    mkdir -p $init_runs_base_dir

    echo "Running maven install on $project_path"
    cd $project_path
    mvn clean install -pl $module -am $MVNINSTALLOPTIONS -DskipTests
    cd -

    echo "Running maven install on $module_path"
    echo "And saving the logs in $init_runs_base_dir/maven_log.log"
    cd $module_path
    rm -rf $init_runs_base_dir/surefire-reports
    mkdir -p $init_runs_base_dir/surefire-reports
    mvn test $MVNINSTALLOPTIONS 2>&1 | tee $init_runs_base_dir/maven_log.log
    cp $module_path/target/surefire-reports/* $init_runs_base_dir/surefire-reports/
    cd -
}


run_maven_command() {
    local order_to_run=$1
    local save_order_dir=$2
    # local num_of_executions=$3

    # if order_to_run is not a file, then return
    if [ ! -f $order_to_run ]; then
        echo "Order file not found: $order_to_run"
        return
    fi

    cd $module_path

    rm -rf target

    mkdir -p $save_order_dir

    run_trials=0

    for iteratiion in $(seq 1 $num_of_executions); do
        # if [ $iteratiion -eq $num_of_executions ]; then
        #     break
        # fi
        mkdir -p $save_order_dir/$iteratiion
        while true; do
            rm -rf $save_order_dir/$iteratiion/*
            echo "Running test order: $order_to_run"
            mvn test -Dtest=$order_to_run -Dsurefire.runOrder=testorder $MVNINSTALLOPTIONS 2>&1 | tee $save_order_dir/$iteratiion.log
            cp $module_path/target/surefire-reports/* $save_order_dir/$iteratiion/
            # if [ "$(ls -A $save_order_dir/1)" ]; then if there are some xml files in the surefire-reports directory then break
            if [ "$(ls -A $save_order_dir/1 | grep .xml)" ]; then
                break
            fi
            three_try=0
            while [ $three_try -lt 3 ]; do
                cp $module_path/target/surefire-reports/* $save_order_dir/$iteratiion/
                if [ "$(ls -A $save_order_dir/$iteratiion | grep .xml)" ]; then
                    break
                fi
                three_try=$((three_try+1))
            done
            if [ "$(ls -A $save_order_dir/$iteratiion | grep .xml)" ]; then
                break
            fi
            run_trials=$((run_trials+1))
            if [ $run_trials -eq 3 ]; then
                break
            fi
        done
    done

    cd -
}



# calculate the test list using the recently run maven install command
create_mvn_instance
fix_project_for_init_run
run_init_maven_test

cd $script_dir #this is the dir where i have the get_test_list.py and the runs/ dir consisting of the initial run log and initial run surefire reports
python3 get_test_list.py $init_runs_base_dir/surefire-reports/ $init_test_list

# the above command create a test list for the module in the test_list directory represented by the var init_test_list
# Now we have to generate random test orders
cd $script_dir
# UNCOMMENT BELOW 2 LINES TO GENERATE NEW TEST ORDERS
mkdir -p $test_orders_base_dir
timeout 15m python3 generate_orders.py $init_test_list $test_orders_base_dir $module_id 26

rm -rf $execution_time_record_dir
mkdir -p $execution_time_record_dir
rm $execution_time_record_dir/$module_id.csv
echo "order_file_name,time_spent" > $execution_time_record_dir/$module_id.csv

# setup the custom surefire on the maven instance
setup_custom_surefire_on_mvn_instance

# Now we run the 100 random orders and save their runtime logs
# for order_file in $(seq 1 $num_of_orders); do
done_order=0
order_index=1

while true; do
    start_time=$(date +%s)
    order_file="$test_orders_base_dir/$module_id/$order_index.txt"
    order_file_name=$(basename $order_file)
    order_file_name="${order_file_name%.*}"
    run_maven_command $order_file $runs_base_dir/$order_file_name 1
    end_time=$(date +%s)

    time_spend=$(echo "$end_time - $start_time" | bc)

    # save the order_file_name and the time_spend in a csv file (/scratch/tbaral/suzzana/time_record/$module_id.csv)
    echo "$order_file_name,$time_spend" >> $execution_time_record_dir/$module_id.csv

    # if there are 100 surefire reports copied in the runs_base_dir then break
    if [ "$(ls -A $runs_base_dir/$order_file_name/1 | grep .xml)" ]; then
        done_order=$((done_order+1))
    fi

    python3 get_runtime.py $module_id $order_file_name $script_dir

    order_index=$((order_index+1))

    if [ $order_index -eq $num_of_orders ]; then
        break
    fi
done
